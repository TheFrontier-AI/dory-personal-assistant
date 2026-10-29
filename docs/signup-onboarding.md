# Sign-up and onboarding (`/start`)

Design note for the flow a new Dory user goes through. Code map entry: `CLAUDE.md`, "Sign-up and onboarding".

## What the person sees

| # | Screen | What it asks | Why it is there |
| --- | --- | --- | --- |
| 1 | Account | Nothing typed: one Google button (a Discord button when Discord sign-in is configured) | The provider proves the email, so there is no password, no verification email and no marketing checkbox. The first screen says what Dory is, what is free, links the Terms and Privacy Policy ("By continuing, you agree...") and has a visible "Already have an account? Sign in" (to `/center`, which is the sign-in). |
| 2 | Organization | One field: the organization name | Chat, tasks and documents belong to an organization, so this is the one thing Dory cannot work without. "Nothing is charged" sits on this form. |
| 3 | Welcome + preferences | Two optional selects: home airport, preferred currency | Welcomes the person, says in three lines what Dory can do, then offers the two choices that improve travel searches. **Save and continue** waits for the server; **Skip for now** moves on at once. Both end the step for good. |
| 4 | Start | Nothing | Three example requests (the first uses the home airport) and the primary action **Start chatting with Dory**. Adding Dory to Discord is optional and tucked in a closed `<details>`. |

The previous plan screen is gone: the launch has a single plan (the free trial), so there was nothing to choose.
Everything on the page is Thai or English (the account's saved language wins over the browser's).

## Decisions

- **Optional means optional.** Nothing is preselected, Skip never waits for the network, and the same two fields live on **My profile** (`/center#/account`), so nobody has to answer now.
- **Examples fill the chat box, they never send.** An example is a link; its text travels in `sessionStorage` (`dory_chat_prefill`, this tab, ten minutes, read once). Dory is not asked anything until the person presses Send.
- **Resume is derived from facts, not from a stored step.** No organization -> organization step. An organization created in this tab whose travel step never ended -> back to that step (a reload, or the Discord round trip). Anyone else with an organization is a returning member and sees "You already have an organization", with a "Travel preferences" button; nobody who already has an account is forced through onboarding. The `onboarded` stamp is set by saving *and* by skipping, so a person who answered is never asked again from another device.
- **Back navigation only where it is safe.** From the examples, Back returns to the preferences with the choices kept. The preferences cannot go back to the organization step: the organization already exists, and a second Create with another name would make a second organization.
- **No permissions before they are needed.** No location, microphone or notification prompt anywhere in sign-up. The home airport is picked from a list, not detected.
- **Honest about what the preferences do.** The home airport is the departure when a flight request names none (`CardCtx.home`, plus a line in Dory's prompt about the person). The currency is stored and told to Dory, but the sample catalogue is priced in THB and Dory is told never to guess a rate; the page says "Sample prices are in THB for now".

## Authentication: real versus demo

There is no demo sign-up. When Google sign-in is not configured the first screen shows "Google sign-in isn't available yet" and nothing is created. An account exists only after a real Google or Discord sign-in, and an organization only after `POST /api/center/orgs` succeeds. (`/center?mock=1` is a separate, clearly labelled mock of the command center, not a sign-up.)

Required configuration (all existing, none added by this flow):

- `HUB_GOOGLE_CLIENT_ID`: the Web client; its "Authorized JavaScript origins" must list the page's origin.
- `DORY_SESSION_SECRET` (Secret Manager `dory-session-secret`): turns the one-hour Google token into a 30-day Dory session.
- Optional: `DORY_DISCORD_CLIENT_ID` + `DORY_DISCORD_CLIENT_SECRET` for "Or sign up with Discord" (a verified Discord email is required) and for the invite link in step 4.

## API

`PUT /api/center/me/travel` with `{home_airport?, currency?, skip?}` answers the person (`GET /me`), which now also carries `home_airport`, `currency` and `onboarded`.
`null` leaves a value as it is, `""` or `"none"` clears it, `skip: true` only stamps the step. An airport outside the search catalogue (`travel_search.AIRPORTS`) or a currency that is not a 3-letter code or a known name is a 422 and nothing is saved.
Dory can set both from a chat or a call with `update_my_profile(home_airport=..., currency=...)`.

## Assumptions and limits

- Only Google and Discord exist as sign-in methods, so there is no password, show/hide control or strength meter, and no email-verification screen of Dory's own. Verification is the provider's; Discord without a verified email gets a plain explanation.
- There is no marketing consent control because nothing is collected for marketing. If that changes, it must be a separate unchecked box.
- The airport list is the six airports of the sample search catalogue. A real airport list needs a real search provider first.
- Invited members open `/center` through the invite link and never see `/start`; they get the same two fields on My profile.
- The currency list is a fixed set of twelve common currencies; the server accepts any 3-letter code.
