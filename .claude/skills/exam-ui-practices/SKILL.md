---
name: exam-ui-practices
description: Project-tailored Angular 21 conventions for the Exam-Prep-App frontend. Use when adding or changing pages, components, routes, signals/state, HTTP calls, SCSS/styling, mobile layout, or Chart.js views in frontend/.
---

# Exam UI Practices (project-tailored)

Single source of truth for frontend conventions in this repo. Everything below
describes what `frontend/src/app` actually does — deliberate departures from
generic Angular advice are marked **(deviation)** with the reason. Backend
conventions live in the sibling `exam-api-practices` skill.

## Stack (do not "upgrade" these choices)

| Concern   | Choice                                              | Do NOT add                                        |
|-----------|------------------------------------------------------|---------------------------------------------------|
| Framework | Angular 21, **standalone only**, zoneless            | NgModules, `zone.js`                              |
| Language  | TypeScript 5.9, `strict` + `strictTemplates`         |                                                   |
| Build     | `@angular/build:application` (esbuild)               | webpack config, `environment.ts` files            |
| State     | Angular **signals** (`signal`/`computed`)            | NgRx, a shared store service, `BehaviorSubject`   |
| HTTP      | `HttpClient` via `ExamService`; one auth interceptor | axios, bare `fetch`, a second interceptor         |
| Auth      | `AuthService` + `authGuard` + `authInterceptor`      | a second token store, per-page 401 handling       |
| Styling   | Hand-written SCSS + utilities in `styles.scss`       | Tailwind, Bootstrap, Angular Material, CSS-in-JS  |
| Charts    | Chart.js 4, imperative                               | ng2-charts or another wrapper                     |
| Forms     | `FormsModule` / `ngModel` only                       | Reactive forms                                    |
| RxJS      | 7.8 — only as the `HttpClient` return type           | RxJS state pipelines                              |
| Format    | Prettier (100 cols, single quotes)                   | ESLint (none configured — see Style)              |

## Layout & naming

```
src/app/
├── app.ts / app.html / app.scss     # shell: <nav> + <router-outlet>
├── app.config.ts                    # providers (router, HttpClient)
├── app.routes.ts                    # every route, one line each, lazy
├── components/question-sections/    # the only shared component
├── pages/<kebab-name>/              # 14 route-level pages (incl. login, register)
└── services/
    ├── exam.service.ts              # ALL app HTTP + domain types + pure helpers
    ├── auth.service.ts              # token + current user (signals)
    ├── auth.interceptor.ts          # attaches the token, handles 401 centrally
    └── auth.guard.ts                # authGuard, instructorGuard
```

- A page is a folder `pages/<kebab>/` holding `<kebab>.ts`, `<kebab>.html`,
  `<kebab>.scss` — no `.component.` infix (Angular 21 style).
- Class name is `<Pascal>Page` (`TakeExamPage`, `HistoryDetailPage`); shared
  components are `<Pascal>Component`.
- Selector is `app-` prefixed and matches the folder (`app-take-exam`).
- Always `templateUrl` + `styleUrl` — inline templates/styles appear nowhere.
- Register with a single lazy line in `app.routes.ts`:

```ts
{ path: 'overview', loadComponent: () => import('./pages/overview/overview').then(m => m.OverviewPage) },
```

## Component shape

```ts
@Component({
  selector: 'app-history',
  imports: [FormsModule],
  templateUrl: './history.html',
  styleUrl: './history.scss',
})
export class HistoryPage implements OnInit {
  records = signal<ExamResult[]>([]);
  searchQuery = signal('');
  filteredRecords = computed(() => { ... });

  constructor(private examService: ExamService, private router: Router) {}

  ngOnInit(): void { this.load(); }

  load(): void {
    this.examService.getHistory().subscribe((data) => this.records.set(data));
  }
}
```

- **Constructor injection with `private` params** in components and services.
  `inject()` appears only in the functional guard and interceptor, where the
  framework offers no alternative **(deviation** from current Angular guidance —
  mixing both styles across 15 component files is worse than one consistent old
  one**)**. If you migrate, migrate all of it in a dedicated change.
- `implements OnInit` / `OnDestroy` declared explicitly; public methods
  annotated `: void`.
- Signals first, then `computed()` derivations, then constructor, then methods.
- `input()` signal inputs are used only in the shared component
  (`question-sections.ts:21-23`). Pages read route params instead.

## State

Signals only, local to the page. No shared store, no service holding state
**(deviation** — every page refetches; the app is small and the data is
server-owned**)**.

- **Refetch after mutate:** `deleteExam(id).subscribe(() => this.load())`
  (`exams.ts:182`, `exams.ts:121`). Don't hand-patch local arrays.
- **Copy-on-write updates.** Objects spread, `Map`/`Set` copied:
  ```ts
  this.titleDrafts.set({ ...this.titleDrafts(), [examId]: value });   // exams.ts:96
  const map = new Map(this.answers()); map.set(i, v); this.answers.set(map);
  ```
- **Per-item loading/error keyed by id**, not one global flag:
  `loadingRename`, `renameError`, `loadingTimeLimit`, `timeLimitError` are all
  `signal<Record<string, ...>>` (`exams.ts:114-125`).
- Anything imperative and long-lived (`setInterval` timers, Chart.js instances)
  is stored on the class and torn down in `ngOnDestroy` — see `take-exam.ts`
  (timer + 500 ms debounced autosave) and `overview.ts` (`private charts: Chart[]`).

## Templates

- Built-in control flow only: `@if` / `@else` / `@for (x of xs; track x.id)`.
  `*ngIf`, `*ngFor`, and `CommonModule` appear nowhere — don't reintroduce them.
- Two-way binding on a signal is written split:
  ```html
  [ngModel]="searchQuery()" (ngModelChange)="searchQuery.set($event)"
  ```
- `FormsModule` is imported per component that needs it.
- Prefer a class in the component `.scss` over `style="..."` (76 inline styles
  already exist — don't add more; migrate one when you're already editing it).

## HTTP & domain types

Every request goes through `ExamService` (`services/exam.service.ts`). That file
is also the single home for domain interfaces and pure helpers — pages import
both from it.

```ts
@Injectable({ providedIn: 'root' })
export class ExamService {
  private base = '/api';
  constructor(private http: HttpClient) {}

  listExams(courseId?: string): Observable<ExamSummary[]> {
    let params = new HttpParams();
    if (courseId) params = params.set('course_id', courseId);
    return this.http.get<ExamSummary[]>(`${this.base}/exams`, { params });
  }
}
```

- `private base = '/api'` — a **relative** prefix, resolved by
  `proxy.conf.json` in dev and nginx `proxy_pass` in prod. No environment files,
  no absolute URLs, ever.
- Every method returns `Observable<T>` with an explicit exported interface. The
  backend has no `response_model`, so **these interfaces are the API contract** —
  update them whenever a backend response shape changes.
- List and detail responses are different types where the backend trims payload:
  `getHistory()` returns `ExamResultSummary[]` (no `results`), while
  `getHistoryRecord()` returns the full `ExamResult`. Don't widen the list type
  back — the blobs are what made that endpoint a DoS.
- `HttpParams` for query strings; template literals for path params.
- Pure helpers live here too — `classifyQuestionType`, `countQuestionTypes`,
  `formatAnswerForDisplay`, `matrixRows`, `clozeBlanks`. New shared logic goes
  here, not into a page. (`formatDate`/`formatTime` are currently duplicated
  across pages — if you touch them, hoist rather than copy again.)
- `noPropertyAccessFromIndexSignature` is on, hence `body['course_id']`
  (`exam.service.ts:360`) rather than dot access on an index-signature type.
- Components `.subscribe()` directly and don't unsubscribe — `HttpClient`
  completes. That's fine here; don't add `takeUntilDestroyed` ceremony for it.

## Auth

- `AuthService` (`services/auth.service.ts`) owns the token and the current
  user, both as signals, mirrored into `localStorage`. It is the **only** place
  that reads or writes those keys.
- `authInterceptor` attaches the bearer token and handles **401 centrally**:
  clear the token → navigate to `/login` → rethrow. Do not add per-page 401
  handling; that is what this covers, including the many `.subscribe(fn)` sites
  with no error callback.
  - It must **rethrow**, never `return EMPTY` — completing the observable leaves
    every loading spinner running forever.
  - Requests to `/api/auth/*` are exempt: a bad password is the caller's error to
    display, not a session expiry.
- Routes live under one parent with `canActivateChild: [authGuard]`; `/admin`
  adds `instructorGuard`. New pages go inside that parent and inherit the guard.
- The nav is wrapped in `@if (auth.isLoggedIn())`; instructor-only links check
  `auth.isInstructor()`.
- An expired token is discarded at bootstrap so a page load does not fire six
  requests that all 401 before the redirect lands.

**Anything that survives a failed request must be mirrored to `localStorage`
before the request goes out.** `take-exam.ts` does this for autosave: an expired
token mid-exam otherwise silently loses a student's answers, and the restore path
prefers the local copy when it is newer than the server's `saved_at`.

## Error handling

Three tiers, plus the interceptor's central 401. Keep `catchError` out of pages
unless a case has more than one caller.

1. **Dominant idiom** — unwrap the FastAPI `detail` into a per-item error signal:
   ```ts
   error: (err) => {
     this.renameError.set({ ...this.renameError(), [exam.id]: err?.error?.detail || 'Rename failed.' });
   }
   ```
   (`exams.ts:125`, `upload.ts:224`, `edit-exam.ts:715`). Always the
   `err?.error?.detail || 'Fallback.'` shape.
2. **Coarse cases** — native `alert()` / `confirm()`
   (`take-exam.ts:676`, `in-progress.ts:43`). There is no toast system; don't
   build one for a single call site.
3. **Cosmetic failures** — swallow explicitly: `error: () => {}`, or reset a
   status signal (`error: () => this.autoSaveStatus.set('idle')`,
   `take-exam.ts:665`).

## Styling

- Global tokens and utility classes live in `src/styles.scss`: `.btn` +
  `.btn-primary|secondary|danger|success`, `.card`, `.badge` +
  `.badge-pass|fail|mcq|sata|fib|other`, `.page-title`, `.empty-state`, plus
  bare-element styling for `input`/`textarea`/`select`. Reuse these before
  writing new component CSS.
- Component SCSS is co-located and scoped by Angular's emulated encapsulation.
  Nested SCSS with `&:hover`; `// ── Name ──` banner comments for sections.
- Palette is literal hex, not variables: `#111` text/primary, `#fafafa` page
  background, `#e8e8e8` borders, `#0a7` success, `#c00` danger, `#4361ee`
  charts. `:root { --nav-height: 55px; }` is the only custom property.
- Layout is flexbox, content capped at `max-width: 860px` (`app.scss:46`).
- Per-component style budget: 12 kB warn / 24 kB error (`angular.json`).

## Mobile

One breakpoint: **`@media (max-width: 640px)`**, used in 13 of 15 SCSS files.
New pages honor the same rules (established by commit `2de6cd5`):

- 44 px minimum touch targets on buttons, inputs, and selects
  (`styles.scss:156-173`).
- `font-size: 1rem` on inputs — `// prevents iOS zoom on focus`
  (`styles.scss:167`).
- `env(safe-area-inset-*)` padding for notched phones (`styles.scss:186-187`,
  `app.scss:62`).
- The top nav becomes a **fixed bottom tab bar**, with the page compensating
  via `padding-bottom: calc(60px + env(safe-area-inset-bottom))`
  (`app.scss:52-125`).

Don't introduce a fourth breakpoint value. (`documents.scss:319` at 600px and
`flashcards.scss:172` at 520px are pre-existing strays, not precedent.)

## Style & tooling

- **Prettier only** — `.prettierrc`: `printWidth: 100`, `singleQuote: true`,
  `parser: angular` for `*.html`. There is no `format` npm script; formatting is
  editor-driven. **No ESLint at all** — don't reference lint rules that don't
  exist.
- `.editorconfig`: 2-space indent, final newline, trimmed trailing whitespace.
- `tsconfig.json` is strict everywhere including `strictTemplates`,
  `noImplicitReturns`, `noPropertyAccessFromIndexSignature`. Respect it rather
  than casting around it.
- JSDoc one-liners (`/** ... */`) on exported interfaces and non-obvious methods.

## Tests

**There are none, and `npm test` cannot currently run** — `tsconfig.spec.json`
references `vitest/globals` but vitest isn't installed, `angular.json` has no
`test` target, and schematics are `skipTests: true`.

Do not generate `.spec.ts` files that can't execute. If tests are wanted,
installing and wiring vitest is a deliberate separate change — propose it, don't
smuggle it in.

## Anti-patterns (check every diff)

| Anti-pattern | Fix |
|---|---|
| `inject()` alongside constructor DI | constructor injection, matching the other 13 files |
| `*ngIf` / `*ngFor` / `CommonModule` | `@if` / `@for (…; track …)` |
| `[(ngModel)]` on a signal | split `[ngModel]="x()"` + `(ngModelChange)="x.set($event)"` |
| `fetch` / axios / an absolute API URL in a page | add a method to `ExamService` using `${this.base}` |
| A helper or interface defined in a page and reused elsewhere | move it to `exam.service.ts` |
| Mutating a signal's array/Map in place | copy-on-write, then `.set()` |
| One global `loading`/`error` flag for a per-row action | `signal<Record<string, …>>` keyed by id |
| A new toast/notification system, a second interceptor, or a state library | the existing 3-tier error idiom |
| Per-page 401 handling | the interceptor already redirects |
| `return EMPTY` in an interceptor | rethrow, or spinners hang forever |
| Reading the auth token outside `AuthService` | inject `AuthService` |
| A new route declared outside the guarded parent | nest it — otherwise it is public |
| Destructive/long-lived local state with no `localStorage` mirror | mirror before the request, like `take-exam` autosave |
| Tailwind or any CSS framework | `styles.scss` utilities + component SCSS |
| New inline `style="…"` in a template | a class in the component `.scss` |
| A new breakpoint instead of 640px | `@media (max-width: 640px)` |
| Adding `.spec.ts` files | no runner is installed — propose wiring vitest first |
| `setInterval` / Chart.js instance without `ngOnDestroy` teardown | store it on the class and destroy it |
