# linkedin

Initially created at ~/code/private-research/linkedin-cli/

## Fix need for initial tab to be open, 27 Jul 2026

<!--
cd ~/code/scripts/
dev.sh -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Modify linkedin.py (and tests/test_linkedin.py) to not require an initial LinkedIn tab to be open.
Assume CDP at localhost:9222 is logged in.
Use this as an opportunity to SHORTEN and simplify the code, not increase it.

<!-- codex resume 019fa297-e100-7f53-91da-3af1f50730c5 --yolo -->

<!-- #TODO: Maybe extend linkedin.py to cover /recent-activity/all/ and /details/{certifications,volunteering-experiences,projects,skills,recommendations,courses,honors,interests,languages}
