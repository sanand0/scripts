# fish_usage.py

## Include scripts, 22 Aug 2026

<!-- https://chatgpt.com/c/6a6c4173-9404-83ec-9fea-af4478777bd0 -->

On @LocalMCP Update `fish_usage.py` to compute the usage of the scripts in ~/code/scripts/ as well (apart from the functions).

These scripts might be part of a pipeline (`|`) so, may not be the first command in the shell.
A naive search for the script name might not be the best way either.
I am okay to count failures - my aim is to capture intended use. But not when it is inside a string or in a comment or whatever.

Go through the full fish history. Iterate and revise until you are happy that this does a good job of capturing the usage of the scripts in this directory.
My aim is to get an intuition for what is used more, what is less used, and how this is changing.

---

OK. Add tests in a manner consistent with the repo, run and test. Prefer real scenarios for test cases.

---

`git-size`, `git-stage-repo`, `git-uncommitted`, etc. will be used as `git size`, `git stage-repo`, and `git uncommitted`. Can we factor this in without adding too much to the code?

## Count fish function usage, 31 Jul 2026

<!-- https://chatgpt.com/c/6a6c4173-9404-83ec-9fea-af4478777bd0 -->
