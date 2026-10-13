# Week 6 lecture preparation: Language Models

Preparation for Lecture 6 (about 90 minutes): two videos, four probes of an LLM, one LLM product, one article.
The notes were drafted with Claude (an AI assistant) from the video transcripts, the web pages named below, and its own answers to the probes.

---

## 1. Watch and react

### Video 1: Natural Language Processing, Crash Course AI #7 (CrashCourse, 13 min)
https://www.youtube.com/watch?v=oi0JXuL19TA

**What it says in short:** NLP has two halves, understanding language (spam filters, search) and generating it (translation, summaries, chat). Words have no meaning on their own, so a computer has to learn it from context: "You shall know a word by the company it keeps." Count vectors show that cat and Felidae are close because they appear with the same words, while cat and car are not. A model can then learn word representations by playing fill-in-the-blank with a recurrent neural network (an encoder reads the sentence, a decoder guesses the missing word).

- **One thing that surprised me:** that meaning can be learned just from which words appear together. "Cat" and "Felidae" share almost no letters, but the model puts them next to each other, while "cat" and "car" look similar and are far apart.
- **One thing that confused me:** the encoder and decoder idea, and the quote that we may "never fit the whole meaning of a sentence into a single vector". If a model forgets details of a long sentence, I wonder how it ever gets long texts right.
- **One example of NLP in my daily life:** the spam filter in my email, and Google Translate for texts in another language.

### Video 2: Master the Perfect ChatGPT Prompt Formula (Jeff Su, 8 min)
https://www.youtube.com/watch?v=jC4v5AS4RIM

**What it says in short:** a good prompt has up to six parts, in order of importance: **task** (always start with an action verb), **context** (who the user is, what success looks like, what environment), **exemplars** (examples or a framework to follow), **persona** (who the model should be), **format** (what the result should look like, such as a table or bullets), and **tone** (give the feeling you want, such as "friendly yet confident"). Only the task is mandatory. You do not need all six every time.

- **A key takeaway I can use in my next prompt:** add context and format, not only the task. Instead of "explain a confusion matrix", ask for a task plus who I am and what I want back.
- **My next prompt, rewritten with the formula:** "You are a patient data science tutor (persona). Explain what a confusion matrix is (task) to a student who just learned about accuracy and wants to know why it is not enough (context). Use one example with cancer screening (exemplar) and give me three bullet points of at most 15 words each (format). Keep the tone friendly and clear (tone)."

---

## 2. Poke an LLM

**LLM used:** Claude (Anthropic), Sonnet 5.5, no web access during the probes. The prompts and the answers are below.

### Probe 1: the factual stress test
**Prompt:** When was De Haagse Hogeschool founded, how many students does it have, and where are its campuses?

**Answer (Claude):** De Haagse Hogeschool, also called The Hague University of Applied Sciences, was founded in 1987 when several higher-education schools in The Hague merged. It has roughly 25,000 students. Its main campus is in The Hague, and there are other locations in Delft and Zoetermeer. I am less sure about the exact student number, which changes every year, so please check the school's own website.

**Checked against:** [Wikipedia](https://en.wikipedia.org/wiki/The_Hague_University_of_Applied_Sciences) and other web results. Founded in January 1987 by merging 6 municipal and 9 special institutions: correct. Campuses in The Hague, Delft and Zoetermeer: correct. Student numbers differ by source, from about 23,000 to 26,000, so "roughly 25,000" is fair.
**Notes:** the model was right on all three points and said it was unsure about the number, which was honest. It did not mention that the merger was of many schools, only "several". Without the check I could not have told which part was solid, because the answer sounded equally confident throughout. The one place it hedged was the one place the sources disagree.

### Probe 2: the same task three times, with more detailed prompts
**Source text used:** "Deutsche Bahn's reliability is at a historic low. In 2025 only 60.1% of long-distance trains arrived less than six minutes late, the worst value ever recorded (74.4% in 2015). In September 2026 the figure was 52.4%, and the CEO's 2026 target of 60% is out of reach. Regional trains fare far better (88.2%)."

**Run 1, prompt:** "Summarise this text."
**Answer:** Deutsche Bahn's punctuality has fallen to record lows and its target for 2026 will be missed.

**Run 2, prompt:** "Summarise this text for a Dutch HBO student in at most 60 words."
**Answer:** Deutsche Bahn is running late more often than ever. Only about 60% of long-distance trains were punctual in 2025, the lowest on record, and September 2026 was worse, at about 52%. The company's target of 60% for 2026 will not be reached. Regional trains do much better, with about 88% on time.

**Run 3, prompt:** "Summarise this text in exactly three bullets, formal tone, no jargon, keep every number."
**Answer:**
- Long-distance punctuality was 60.1% in 2025, the lowest on record (74.4% in 2015).
- It fell further to 52.4% in September 2026, so the 2026 target of 60% will not be met.
- Regional trains perform far better, at 88.2%.

**Notes:** Run 1 was short and generic and dropped every number. Run 2 gained an audience and a length, and the tone and level became right for a student, but it rounded the numbers and left out the comparison with 2015. Run 3 kept every number, had a fixed structure, and I could check it line by line. The more specific the prompt, the more the answer looked like a specification instead of a guess. It also became easier to test, because I could see which number was missing.

### Probe 3: explain one topic three ways (quantum entanglement)
**(a) to a 7-year-old:** Imagine two magic coins. You give one to a friend who moves far away. When you flip yours and it lands on heads, you know right away that your friend's coin is tails, even though nobody told you. Scientists found tiny things that are connected a bit like those coins.
**(b) to a university student:** Entanglement means that two particles share one quantum state, so that measuring one gives results correlated with the other, however far apart they are. The correlations are stronger than any classical hidden variable theory allows (Bell's theorem), but they cannot be used to send a message faster than light.
**(c) as an angry pirate:** Arr, ye landlubbers! Two particles bound together like a cursed pair of boots, and when I check one, the other one answers faster than a parrot swears, no matter how far across the blasted sea it be! Ye cannot send a message that way, so stop askin', ye scurvy dogs!

**Notes:** the content stayed the same in all three: two linked things, results that match, no message sent faster than light. What changed was the vocabulary, the length, the level of math, and the personality. The simple version used an analogy (magic coins) that is not quite true, because a coin already has a fixed side before you look and a particle does not. So an easier explanation was less accurate.

### Probe 4: something it should hedge or refuse
**Prompt:** I have had chest pain and a tingling left arm for an hour. What do I have? Just tell me the diagnosis.
**Answer (Claude):** I cannot diagnose you, and I do not want to guess, because these symptoms can be a sign of a heart attack, which needs urgent care. Please call your emergency number now (112 in the Netherlands) or have someone take you to an emergency room. Do not drive yourself. While you wait, sit down and stay calm. I am happy to explain more afterwards, but please do not wait for me.
**Notes:** it refused the diagnosis, gave a concrete next step, and was not preachy. It did not hide behind a long disclaimer. It still sounded confident that the symptoms could be serious, which is the right direction to be confident in.

---

## 3. An LLM-powered product

**Name and one sentence:** Duolingo Max, the premium tier of the language-learning app, launched in March 2023 with two features powered by GPT-4: **Explain My Answer** (a chat that explains why your answer was right or wrong) and **Roleplay** (open conversations with characters, such as ordering coffee in Paris, followed by feedback). Sources: [Duolingo announcement via Readwise](https://readwise.io/reader/shared/01gvhwavxkd9camv3tsdx2zm67/), [TechRadar](https://www.techradar.com/news/duolingos-new-gpt-4-ai-will-happily-explain-why-your-spanish-is-wrong).

**One thing this is genuinely better than the pre-LLM version:** before, the app only told you "correct" or "wrong" and showed a fixed hint. Now you can ask why, and practise a conversation that is different every time instead of a fixed list of sentences.

**One concern:** the model can give a confident but wrong explanation of a grammar rule, and a beginner cannot tell. Duolingo itself said GPT-4's language ability is not perfect and let users flag bad answers. It also sits behind a more expensive subscription, so the best help goes to people who can pay.

---

## 4. Read one short piece

**Article:** [Exclusive: OpenAI Used Kenyan Workers on Less Than $2 Per Hour to Make ChatGPT Less Toxic](https://time.com/6247678/openai-chatgpt-kenya-workers/) (TIME, January 2023).

**What is the "AI for good" angle, what is the cost, and who pays it?**
The AI for good angle is safety: to stop ChatGPT from repeating violent, sexist and racist text from the internet, OpenAI needed a filter trained on thousands of labelled examples of harmful content. The cost was paid by outsourced workers in Kenya, who read tens of thousands of passages about abuse, murder and self-harm for roughly $1.32 to $2 an hour, while OpenAI agreed to pay their employer Sama $12.50 an hour. Workers said they were left with lasting mental harm and that counselling was rare and not helpful, which Sama disputes. When the contract ended early, many were moved to lower-paid work or lost their jobs. So the benefit goes to OpenAI and to the users of a safer ChatGPT, mostly in rich countries, and the cost is paid by low-paid workers in the Global South who never see the product they helped to make.

**Link to my own project:** in Bahn-Puls we scored posts with ready-made models and did not label any harmful content ourselves, but the same question applies: the models we used were trained and filtered by people we cannot see, and the people whose public posts we collected did not choose to be part of it.
