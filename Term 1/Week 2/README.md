# Term 1 - Week 2: Loops & Functions

---

## 1. Homework & workshop assignments -> [`homework/`](homework/)

**What was the assignment? The Week 2 topic was loops and functions. Add the exact homework/workshop brief here, because it was not included with the GymTrack files.

we hand in a Json file and a pptx file and a telegram link to the chat for it to work
**What did I find difficult, and how did I solve it?**

### Checklist
- [y] My workshop / homework files are in `homework/`
- [y] Everything runs without errors, or I explained what does not and why

---


## 2. Hackathon prototype -> [`hackathon/`](hackathon/)

> Your tool and your SDG for this hackathon are announced at the **start of Friday's class**.
> Write them down here once you know them.

**Project title:GymTrack Workout Coach

**My pair partner:Jou

**Tool we had to use: n8n

**SDG we had to address:SDG 3 — Good Health and Well-being

**What problem does it solve, and for whom?**
GymTrack is for people who are new to the gym and want an easy way to remember and track their workouts. Beginners can forget what exercises, weights, sets, repetitions, cardio, or steps they completed earlier in the week. This makes it harder to see progress and plan the next workout safely. GymTrack lets them log a workout in Telegram and receive a short response based on their recent workout history.

**What did you build?**
We built an n8n workflow called GymTrack Workout Coach. A user sends a workout message through Telegram, such as exercises, sets, reps, weight, cardio, or steps. The workflow reads recent history from Google Sheets, uses an OpenAI chat model to create concise feedback and a next-session target, stores the new entry in Google Sheets, and sends the response back to the same Telegram chat.

The workflow includes a Telegram trigger, Google Sheets history and recording, a JavaScript preparation step, window memory, an AI coaching agent, and a Telegram response step.


**Link to the live thing (if any):**
[_Deployed URL, workflow export, video demo - whatever proves it works._](https://t.me/PersonalTrainer63919_bot)

**How do I run it?**
first access the link text /start then tell it what you didi today it will keep track of your work out and give tip

**Who did what?**
D. L. Dinh: Developed the GymTrack idea and user flow; built and tested the n8n workflow with ChatGPT; prepared the documentation, screenshots, slides, and presentation materials.

Jou: Contributed to the project review, testing, feedback, and presentation preparation.

Both partners: Discussed the SDG 3 problem, reviewed the workflow, tested the Telegram-to-feedback flow, and prepared the final submission.

**Ethical reflection - what are the risks of your tool? Who could it harm?**
GymTrack provides automated exercise feedback, which a user may interpret as guidance from a licensed personal trainer or healthcare provider. Beginners, those with disabilities, chronic illnesses, injuries, or those returning to exercise after illness may find this dangerous. A person may be encouraged to lift too much, train the same muscle region too quickly, or ignore pain by inaccurate or overconfident feedback, which could result in overtraining or injury. Users' fitness data must be treated properly because the tool also saves workout messages and AI feedback in Google Sheets. GymTrack should make it very obvious that it is not a substitute for a human trainer or medical advice, but rather a general tracking and motivational tool. For injuries, illnesses, or customized training regimens, it should motivate users to stop when they experience discomfort and seek advice from a licensed trainer or medical expert. We would include safer limitations for beginner recommendations, more explicit cautions, and an option to remove stored workout data in a later release.
### Checklist
- [y] Prototype code (or export / workflow file) is in `hackathon/`
- [y] This week's slides are in `hackathon/`
- [y] The prototype actually runs, and I wrote down how to run it
- [y] Ethical reflection written above

---

## 3. Presentation -> [`presentation/`](presentation/)

*Only fill this in for the week your group was selected to present. You need at least **one** of these across the whole term.*

- [ ] My group presented in this week
- [ ] Slides are in `presentation/`
- [ ] Proof of the live demo is in `presentation/` (recording, screenshots, or link)

**How did it go? What would I do differently next time?**
From a Telegram exercise message to recorded workout history and customized feedback, the prototype demonstrated a clear flow. The next time, we would add a clearer disclaimer in the chat answer, test more beginner and safety-related workout messages earlier, and have a quick backup video ready in case Telegram, n8n, or the internet fail during the presentation.
---

## 4. Reflection

**What is the most important thing I learned this week?**
I discovered that several services can be combined into a single, practical product using an automation methodology. Telegram, Google Sheets, RAM, JavaScript data preparation, and an AI model were all clearly coupled by n8n. I also discovered that it's important to test the entire input-to-output flow since each node needs to provide accurate data to the subsequent node.
**Where does this connect to "AI for Good"?**
GymTrack helps new gym patrons develop a regular exercise routine and track their progress, which links to SDG 3: Good Health and Well-Being. But responsible use is crucial: AI feedback must assist users without posing as a substitute for a human coach or medical expert. When necessary, the tool should promote rest, safe training, and expert assistance.
