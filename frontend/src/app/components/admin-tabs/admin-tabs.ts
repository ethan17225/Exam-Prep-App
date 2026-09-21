import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

/**
 * Sub-navigation shared by the four admin console pages.
 *
 * The console is four routes rather than one page with tab state, so each keeps
 * its own bundle, URL and back-button behaviour — but they need one visible tab
 * strip, and that is this component. It is the only shared component with no
 * inputs: every link is static.
 */
@Component({
  selector: 'app-admin-tabs',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './admin-tabs.html',
  styleUrl: './admin-tabs.scss',
})
export class AdminTabsComponent {}
