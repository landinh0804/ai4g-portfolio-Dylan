# Ethical reflection: Late Hague

## What the app assumes about the user
- Language: the app is in English only. A student who does not read English will have trouble.
- Device and internet: a smartphone or laptop with a browser and internet. The map and the places need a connection.
- Knowledge: the user knows which kind of place suits them. The app does not know if a café allows studying, if it is quiet or if it is busy.
- Mobility and accessibility: the app has no information about step-free entrances or toilets. A student who needs this gets no help from it.

## Who is left out
- Students without a smartphone or without data.
- Students who need accessibility information.
- Students who live far outside the centre. Most places in the data are in the centre.
- Places that nobody has mapped well. OpenStreetMap is made by volunteers, so places without opening hours are shown as unknown. Only about a third of the places have hours, so many real places are missing or wrong.

## What can go wrong for the user
- A student walks to a place at night and it is closed because the hours in the data are old or wrong. This is the main risk, because it can mean a long walk alone late at night. What I did about it: places with no hours are never shown as open, the page says when it shows saved data, the official HHS library hours link to the HHS page, and every place has a link to report wrong hours on OpenStreetMap.
- The Study tab shows cafés and bars. At 23:00 all three results in my test were bars or cafés, so the app can send students to a place that sells alcohol. I did not filter this. What I would do next: label bars clearly, or let the student choose "no bars".
- A student trusts the app more than they should. The app does not say a place is good for studying, only that it is open.

## How the tool can be used for the wrong reasons
The app has no accounts and no student data. The risk of misuse is small. Someone could use it to find where late-night places are, for example to find alcohol late at night, which is not what I built it for. Someone could also copy the saved data, but that data is public OpenStreetMap data.

## Privacy
- No login, no ads and no tracking.
- The Near me button asks for the location only when a student presses it. I asked Lovable to keep the location on the device and not send it anywhere. Lovable says it did this. I did not read the code and I could not test the button, so I have not checked it myself.
- The requests for places go from the student's browser to OpenStreetMap servers, so those servers can see the student's IP address.

## Data and licence
- The places come from OpenStreetMap contributors (ODbL licence). The page shows the credit and a link.
- The HHS library hours are copied by hand from the HHS page on 5 Nov 2026 and can change. Holiday hours differ.

## What I would do next
1. Ask other HHS students where they study after 20:00, so I have real numbers for the problem.
2. Label or filter bars on the Study tab.
3. Read the code with someone who can check it, especially the location part.
4. Show the first results from the saved copy right away, and update them when the live data arrives.
