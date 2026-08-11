# Documents are shared reading material for every logged-in user: they live on
# disk with no per-user story, and there is no upload endpoint. The mount is
# authenticated by middleware, not authorized per file.
DOCS_URL_PREFIX = "/docs-files"
