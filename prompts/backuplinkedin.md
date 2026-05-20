# backup_linkedin.py

## Initial script, 19 May 2026

<!--
cd ~/code/scripts
dev.sh -v /home/sanand/Documents/data/:/home/sanand/Documents/data/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write an agent-friendly script `backup_linkedin.py` that allows sub-commands to use CDP to scrape and back up my LinkedIn data that are not exported by default.

Let's start with posts.

```bash
backup_linkedin.py posts --username sanand0
```

... should visit https://www.linkedin.com/in/sanand0/recent-activity/all/ on CDP 9222 and:

- Click on the "More" button of each post to copy the content, along with
  - links to all media (images, videos, documents) in the post.
  - when it was posted - converting 2h, 1d, 1w, etc. into best effort timestamps.
  - number of links, comments, reposts, impressions, etc.
  - timestamp of when the post was scraped.
  - click on the "comments" button to list all comments, including
    - who commented: name, profile link, description, type (e.g. verified, premium, etc.)
    - when they commented - converting 2h, 1d, 1w, etc. into best effort timestamps.
    - content of the comment - clicking on "more" if required
    - whether it was edited
    - how many reactions it received and of what types
    - number of replies to the comment if any
    - number of impressions if available
    - parent comment - if it is a comment to a comment
    - click on the load more comments button / see previous replies button until all comments are loaded.
- Scrolling down to repeat the above, loading more posts as it scrolls or clicking the "Show more results" button

Wait till relevant content is loaded, as you scroll, before scraping.
Use robust DOM selectors that are least likely to change with UI updates and add fallbacks where you think they'll be required.
Log errors/warnings for unexpected page structures, missing elements, etc. to help with debugging when LinkedIn updates their UI.
Review and apply best practices from other scripts like `backupwhatsapp.py`, etc.

Save the output as a JSONL file `/home/sanand/Documents/data/linkedin-posts.jsonl` with one JSON object per post or comment (use "type" to distinguish, include a parent id to identify which post a comment belongs to), containing all the scraped information.

When the script is run again, it should update or append new posts/comments to the same file without duplicating existing ones. Updates are required because statistics like number of reactions, comments, impressions, etc. can change over time. Even content can change if the post/comment is edited. Use post/comment IDs to check for duplicates.

Run this for 100 posts. Review the content and output and suggest improvements, e.g. what additional fields are easy to capture and are worth capturing, how to better handle timestamps, how to speed up the capture, how easy is it to capture who reposted and is it worth it, how easy is it to sort comments by recency rather than relevance and is it worth it, etc.

---

Copy the output to ./linkedin-posts.jsonl in the local directory and use that as the output going forward to test and ensure that (a) the output file can be anywhere and (b) will be updated in place rather than content getting deleted or duplicated.

Did the script capture all replies - e.g. "See previous replies" in comments, etc. Review the DOM and validate. If it didn't fix that before you re-run.

Review the DOM to see if there are any other useful pieces of information that need to be captured. Document them - no need to re-run. I'll guide you on which ones to prioritize.

---

Update the script to capture these additional fields:

- `analyticsUrl`
- `authorMiniProfileUrn`
- `commenterMiniProfileUrn`
- `reactionTypesVisible`
- `commenterDegree`
- `premiumVerifiedBadges`

Test on a sample and make sure it updates ./linkedin-posts.jsonl in place without duplication.

Tell me how to run it for all posts.

<!-- codex resume 019e401d-968d-7112-a82e-a2e6bf03edae --yolo -->

---

NOTE: I renamed `backup_linkedin.py` to `backuplinkedin.py` for consistency.
