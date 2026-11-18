# MySQL init scripts

Put a verified dump of the old production schema/data in this directory before bootstrapping a brand-new MySQL container.

Recommended order:

1. `000-old-system-dump.sql` exported from the old MySQL database.
2. `001-media-import-job.sql` for the new Douyin import job table.

For production migration, prefer restoring the old dump manually and verifying row counts before starting the new API.
