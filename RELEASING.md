# Releasing SAT-xtreme

HACS shows the GitHub releases of this repository as versions and offers new releases as updates.
Once a release exists, HACS no longer installs plain commits, so every change reaches users through a
release.

## Version format

`<upstream version>-xtreme.<N>`, for example `4.2.1-xtreme.12`.

- Use a `-`, not a `+`: AwesomeVersion (used by Home Assistant and HACS) ignores everything after a `+`.
- `N` only goes up. When the fork moves to a new upstream version, it becomes for example
  `4.3.0-xtreme.1`.
- The git tag is exactly the version in `custom_components/sat/manifest.json`, without a `v`.

## Steps

1. Raise the version in `custom_components/sat/manifest.json`.
2. Add an entry to `CHANGES_XTREME.md` whose heading contains the version in backticks, for example
   ``## Version 13: ... (`4.2.1-xtreme.13`, <date>)``, with what changed, the switch (if any), and the
   files.
3. Run the tests; all must pass (`tests/test_version.py` checks the version format and the
   `CHANGES_XTREME.md` entry):

   ```bash
   python -m pytest tests
   ```

4. Commit the changes.
5. Create an annotated tag on that commit:

   ```bash
   git tag -a 4.2.1-xtreme.13 -m "SAT-xtreme 4.2.1-xtreme.13"
   ```

6. Push the branch and the tag:

   ```bash
   git push <remote> xtreme
   git push <remote> 4.2.1-xtreme.13
   ```

7. Create the GitHub release from the tag (website: *Releases → Draft a new release*, or
   `gh release create <tag> --verify-tag --title "SAT-xtreme <tag>" --notes-file <file>`):
   - title: `SAT-xtreme <version>`;
   - notes in English, based on the `CHANGES_XTREME.md` entry: what changed, which switches exist, that
     everything new is off by default, and a link to the README;
   - not marked as pre-release (unless it really is a test version).

## Checking in HACS

*HACS → SAT-xtreme → ⋮ → Update information* shows the new version. *⋮ → Redownload* lets you pick an
earlier release to go back to.
