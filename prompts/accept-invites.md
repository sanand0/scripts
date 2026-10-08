# accept-invites

## Initial version, 05 Oct 2026

<!-- Create accept invites script: https://chatgpt.com/c/6ac372a9-7cec-83ec-ae67-bd7f4755dbb6 (2026-10-05T18:18:58+08:00) -->

On @LocalMCP2 write a script accept-invites that does the following.

Using `gws`, accept all invites from s.anand@straive.com to root.node@gmail.com. And vice versa. Then delete all the invites. Then delete all the acceptance emails (which may take a bit of time to be received.)

You might want to sequence the steps to give time for the acceptance emails to be sent, e.g. accept mails from one inbox, then accept mails in the other inbox, then delete the acceptance emails in the first, then in the second.

Run and test. You're welcome to create a few invites to each other from my calendars to verify behaviors and edge cases - just delete the invites from all calendars later.

--- <!-- 08 Oct 2026 -->

I moved the script to ~/code/scripts/accept-invites and have been running it. I'd like to expand the scope. For example, I currently have invites in my s.anand@straive.com calendar that are from root.node@gmail.com and they haven't been accepted. Maybe because I deleted those invites (thinking they were accepted). Or whatever. The point is, if there are invites - in the calendar or email - from one email to the other, accept them. Once the invites are accepted - whether the script accepted them now or I had accepted them earlier - delete them. If there are acceptances - either that the script accepted now or I had accepted earlier - delete them.

So you get the idea, right? I'm looking for a synced end-state. Implement this.

BTW, if you think Python is better than a shell script for this, feel free. But if you think a shell script is better, stay with it.
