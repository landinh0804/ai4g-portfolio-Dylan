# DutchLingo — Dutch Vocabulary Learning App with AI Sentence Coach

A vocabulary-learning app for English-speaking adult beginner learners of Dutch, especially international students and newcomers in the Netherlands. Combines flashcards, multiple-choice quizzes, and an AI-powered sentence coach that gives personalised feedback on the learner's own Dutch sentences.

## SDG 4: Quality Education — Problem Definition

**What is going wrong:** English-speaking international students and newcomers in the Netherlands often need practical beginner Dutch for everyday participation. Flashcards can teach word recognition, but they do not show whether someone can use a word appropriately in their own sentence.

**For whom:** English-speaking adult beginner Dutch learners, especially international students and newcomers living in the Netherlands.

**Where/context:** The Netherlands — where daily life, services, and social participation benefit from basic Dutch.

**Why it matters:** Without practical language support, newcomers face barriers to everyday participation. Traditional tools teach recognition but not productive use.

**Evidence placeholder:**
> [ADD VERIFIED SOURCE HERE: source supporting the Dutch-language learning/access challenge for newcomers or international students in the Netherlands]

## Target Users & Conditions of Use

**Intended users:** English-speaking adult beginner learners of Dutch, including international students and newcomers living in the Netherlands.

**Conditions of use:** English literacy, basic digital skills, a phone or computer, reliable internet, and beginner-level learning needs.

**Exclusions/underserved learners:**
- People without English literacy (instructions and feedback are in English)
- Offline users (the app requires a reliable internet connection)
- Learners who need more accessibility support beyond basic keyboard access
- Advanced learners who need professional Dutch, conversation practice, detailed grammar teaching, or pronunciation feedback

## Solution Flow

1. **Learner selects a word** in AI Sentence Coach from the existing Supabase vocabulary
2. **Sees meaning and example** — Dutch word, English translation, category, and example sentence
3. **Writes a Dutch sentence** using the selected target word
4. **Secure server AI processing** — the sentence is sent to a Supabase Edge Function that calls OpenAI server-side (the API key never touches the browser)
5. **Structured feedback** — correct/needs-revision status, overall feedback, corrected sentence, error explanations, encouragement
6. **Revision** — learner can copy the correction, revise, and request feedback again
7. **Private progress update** — learner marks the word as practised, which updates only their own progress record

## Why AI Is Necessary

Flashcards and multiple-choice questions test word **recognition** — can you identify the correct translation? They cannot evaluate whether the learner can **use** the target Dutch word meaningfully in their own sentence and give personalised feedback on grammar, word order, and word usage. The AI Sentence Coach fills this gap by evaluating the learner's own productive output and providing targeted, context-aware corrections and explanations.

## Features

- **Learn Mode** — Flashcard-style introduction of new Dutch words with example sentences
- **Practice Mode** — Multiple-choice quizzes with instant feedback, streaks, and scoring
- **Word Library** — Browse, search, and filter all 100+ words by category; add custom words
- **AI Sentence Coach** — Write your own Dutch sentence using a selected word and get structured AI feedback on grammar, word usage, and word order
- **Private Progress Tracking** — Words move through New → Learning → Mastered based on quiz performance and AI coach practice; progress is private to the authenticated user
- **Leaderboard** — Rank by total points (quizzes only)

## Technical Architecture & AI Security

```
React Client (Vite)
  ├── Supabase Auth (anonymous sign-in on startup, email/password optional)
  ├── Supabase Database (words, user_progress, user_stats, profiles)
  └── Supabase Edge Function: sentence-coach
        ├── Reads OPENAI_API_KEY from server-side env only
        ├── Calls OpenAI API (model: gpt-4.1-mini)
        ├── Validates input and output
        └── Returns structured JSON feedback to client
```

**AI security:**
- The OpenAI API key is read ONLY from the Edge Function's server-side environment variable `OPENAI_API_KEY`. It is never placed in Vite frontend environment variables, source code, browser storage, or committed `.env` files.
- The model name is a single server-side constant: `const MODEL = "gpt-4.1-mini";`
- AI calls are made from the Edge Function, never from the React browser client.
- The function validates request input (word data present, sentence trimmed, non-empty, max 300 characters).
- The function validates the AI's JSON response before returning it to the frontend.
- Learner free-text sentences and AI feedback are NOT persisted to the database by default.

## Per-User RLS Design

All data tables use Row Level Security:

| Table | Policy | Access |
|-------|--------|--------|
| `words` | Public SELECT, authenticated writes | All users can read; only logged-in users can add/edit |
| `user_progress` | Owner-scoped CRUD | `user_id = auth.uid()` — users can only see/modify their own progress |
| `user_stats` | Owner-scoped CRUD + authenticated SELECT for leaderboard | Users see their own stats; all authenticated users can read stats for leaderboard |
| `profiles` | Owner-scoped INSERT/UPDATE, authenticated SELECT | Users manage their own profile; others can see display name for leaderboard |

The `user_progress.user_id` column is `NOT NULL DEFAULT auth.uid()` with a foreign key to `auth.users(id) ON DELETE CASCADE`. This ensures:
- Every progress row belongs to a real authenticated user
- The `DEFAULT auth.uid()` means client inserts that omit `user_id` still succeed
- RLS policies enforce `auth.uid() = user_id` so users can never read or modify another user's progress
- Old anonymous progress rows (from the previous shared model) were deleted as part of the migration — this is documented as a prototype data reset

## Setup

### 1. Frontend environment variables

Create a `.env` file in the project root (see `.env.example`):

```
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key-here
```

### 2. Enable Supabase anonymous auth

1. Open your Supabase dashboard
2. Go to **Authentication** → **Providers**
3. Enable **Anonymous** sign-ins
4. The app will automatically sign users in anonymously on startup. If anonymous auth is not enabled, users will see the email/password sign-in screen as a fallback.

### 3. Apply database migrations

All migrations in `supabase/migrations/` are applied automatically via the Supabase MCP tools. The key migration for this hackathon is `secure_user_progress_rls`, which:
- Deletes old anonymous progress rows (prototype data reset — documented here)
- Adds a foreign key from `user_progress.user_id` to `auth.users(id)`
- Sets `user_id` to `NOT NULL`
- Recreates owner-scoped RLS policies

### 4. Set the OpenAI API key as an Edge Function secret

The Edge Function needs `OPENAI_API_KEY` to call the OpenAI API. Set it as a Supabase Edge Function secret:

**Via Supabase Dashboard:**
1. Go to your Supabase project
2. Navigate to **Edge Functions** → **Secrets**
3. Add a new secret: Name = `OPENAI_API_KEY`, Value = your OpenAI API key

**Via Supabase CLI (if available):**
```bash
supabase secrets set OPENAI_API_KEY=sk-your-key-here
```

### 5. Deploy the Edge Function

The Edge Function source is at `supabase/functions/sentence-coach/index.ts`. Deploy it using the Supabase MCP deploy tool or:

```bash
supabase functions deploy sentence-coach
```

### 6. Run the app locally

The dev server runs automatically. Open the preview to use the app.

## Ethical Risks & Mitigations

| Risk | Likely Impact | Mitigation |
|------|---------------|------------|
| English-only interface and feedback | Excludes non-English-speaking learners | Documented as a known exclusion; future versions could localise the interface |
| Unreliable AI feedback | Learner receives incorrect corrections | Safety disclaimer shown with every response; AI cannot replace a teacher; response validation on server |
| Privacy of learner data | Sensitive practice data exposed | Per-user RLS; free-text sentences not saved by default; anonymous auth prevents identity exposure |
| Device/internet access requirement | Excludes offline or low-device learners | Documented as a known exclusion; app is online-only |
| Limited vocabulary/context | Learner outgrows the app | Documented as beginner-level only; advanced learners directed elsewhere |
| Score misuse / gatekeeping | Scores used to judge someone's Dutch ability | "No gatekeeping" policy in About page; scores are private practice tools, not assessments |

## Demo Script (2-3 minutes)

1. **Open the app** — you are automatically signed in anonymously and see the Dashboard with vocabulary stats
2. **Go to AI Coach** (click "AI Coach" in navigation) — search for a word (e.g. "goedemorgen")
3. **Select the word** — see the Dutch word, English translation, category, and example sentence
4. **Write a Dutch sentence** — e.g. "Goedemorgen, ik heet Anna" or intentionally make an error like "Goedemorgen ik zijn Anna"
5. **Click "Get AI Feedback"** — see structured feedback: correct/needs-revision status with icon, overall feedback, corrected sentence, error explanations, encouragement, and the safety disclaimer
6. **Copy the correction** — click the copy icon to replace your sentence with the corrected version
7. **Revise and request feedback again** — confirm the corrected sentence gets "Correct!" status
8. **Click "Mark word as practised"** — the word's progress updates privately for your account
9. **Go to About** — show the SDG 4 section, responsible use, exclusions, AI limitations, no-gatekeeping policy, and privacy section
10. **Go to Practice** — start a quiz, answer a few questions, see the streak/points feedback

## Testing & Troubleshooting

- **AI feedback not working:** The Edge Function requires `OPENAI_API_KEY` to be set as a Supabase secret. If it's missing, the app shows "AI feedback is not available right now." Check Supabase Dashboard → Edge Functions → Secrets.
- **Supabase connection issues:** Ensure `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set in `.env`. The app loads vocabulary from Supabase — if it can't connect, you'll see a loading error.
- **Anonymous auth not working:** If anonymous sign-in is not enabled in Supabase, the app falls back to the email/password sign-in screen. Enable Anonymous in Supabase Dashboard → Authentication → Providers.
- **Progress not saving:** Ensure you are signed in (anonymous or email). RLS requires `auth.uid() = user_id` — without a session, all writes fail silently.
- **Edge Function not deployed:** The function must be deployed to Supabase. Check Supabase Dashboard → Edge Functions to verify `sentence-coach` is listed.

## Tech Stack

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS
- **Backend:** Supabase (PostgreSQL, Auth, Edge Functions)
- **AI:** OpenAI API (gpt-4.1-mini) via Supabase Edge Function
- **Icons:** lucide-react
- **Vocabulary seeder:** Python script (`scripts/seed_vocabulary.py`)
