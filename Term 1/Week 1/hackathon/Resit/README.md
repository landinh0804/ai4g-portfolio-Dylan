# Late Hague (Hackathon 1 resit)

Live app: https://hague-open-hours.lovable.app/

Tool: Lovable (the brief allows Bolt or Lovable). SDG: 4, Quality Education. Made by Dylan.

## The problem
The main library of De Haagse Hogeschool closes at 22:30 from Monday to Thursday and at 18:00 on Friday. The HHS page lists no weekend hours. The Centrale Bibliotheek closes at 20:00 according to a Magnet.me blog, but that blog has no date, so I treat it as a hint only. A student who wants to study later than that has to guess where to go.

I checked this with my own app. On a Thursday at 23:00 only 3 of 332 study places in OpenStreetMap are tagged as open: Bar Bistro de Twee Heeren, Café Emma and Muziekcafé Musicon. All three are bars or cafés, not study spaces.

What I do not have: a study that says The Hague has a shortage of late study places, and answers from other students. I did not ask them yet. So my evidence is the opening hours, not a count of students who are affected.

## Who it is for
Students of De Haagse Hogeschool, and other higher education students in The Hague, who study in the evening, at night or at weekends and have a smartphone and internet.

Not for: tourists, people who need accessibility information (the app has none), or anyone who wants to know if a place allows studying (the app does not know that).

## How it fits SDG 4
SDG 4 target 4.a is about safe and effective places to learn. My app is about access to a place to study, not about teaching. That is a small part of SDG 4 and I want to be honest about it.

## What the app does, step by step
1. I choose a day and time. The default is now. There are buttons for Tonight 23:00, Friday 20:00 and Saturday 14:00.
2. The app asks OpenStreetMap (the Overpass API) for libraries, cafés and coworking places (Study tab) and for fast food, convenience shops, supermarkets and restaurants (Food tab) in Den Haag.
3. For each place it reads the opening hours tag with the opening_hours package and decides: open, closed or unknown at that time. Unknown is never shown as open.
4. It shows a map and a list in three groups: Open then, Closed then, and Hours unknown (folded away). The Study tab also has a card with the official HHS library hours and a link to the HHS page. Wi-Fi and power badges only show when the data says so.
5. If the OpenStreetMap servers do not answer, the app uses a saved copy of the data from 5 Nov 2026 and says that on the page.

## Why not just use Google Maps
Searching Google Maps for "cafe open now" is the simple alternative. My app is different in these ways: I can check a time in advance, it separates study places from food, it shows the official library hours, it says when the hours are unknown instead of guessing, and it has no account and no tracking. This is not a big difference, and I did not test it against Google Maps with other students.

## How I used Lovable
- I first tried Bolt, but its free tokens ran out in the middle of the build, so I used Lovable.
- Message 1: my full brief (see PROMPTS.md). Lovable built the app and tested it in a phone-sized window.
- Message 2: in my browser the OpenStreetMap server answered with error 503 (overloaded) and the app showed no places. I asked Lovable to try three servers and then use a saved copy of the data. I made that copy from a download of the OpenStreetMap data on 5 Nov 2026 (places_snapshot.json).

All the code was written by Lovable from my prompts. What I did: chose the problem, collected the facts about the opening hours, wrote the prompts, tested the app, found the 503 problem and asked for the fix. I did not read all the code.

## Known limits
- If the OpenStreetMap servers are down, the first load can take up to a minute before the saved data appears.
- Only about a third of the places in OpenStreetMap have opening hours. The saved copy has 2,016 named places and 770 of them have hours.
- The Near me button is not tested, because the test browser cannot share a location.
- The saved copy leaves out 28 colleges and universities, so Live and Saved show the same kinds of places.

## Files in this folder
- README.md: this page
- ETHICS.md: the ethical reflection
- PROMPTS.md: the two prompts I gave Lovable
- places_snapshot.json: the saved data from 5 Nov 2026
- app_tonight_2300.jpg: screenshot of the live app on Thursday 23:00

## How to run
Open the live link in a browser. No account is needed.
