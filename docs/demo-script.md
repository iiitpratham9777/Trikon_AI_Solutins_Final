# Demo script (about 2.5 minutes)

**Before recording:** `ollama serve` running, backend and frontend started, page open at http://localhost:5173, all four status dots green, one warm-up turn already done, headphones on (prevents the mic hearing the reply), browser mic permission already granted.

| Time | Do | Say |
|---|---|---|
| 0:00 | Show the page. Point at the Models panel. | "This is VoxPilot, a voice assistant where every model runs on this laptop: Faster-Whisper for speech recognition, Qwen through Ollama for the answer, and Kokoro for the voice. No cloud AI API is involved." |
| 0:20 | Click the mic, ask: "What is the capital of India, and why was it chosen?" and pause. | "I just speak and pause; it stops listening on its own." |
| 0:40 | While the reply plays, point at the Last response bar. | "These timings are measured per stage on the server: audio decode, speech-to-text, first token and total from the LLM, and speech synthesis. The browser also shows when audio actually started." |
| 1:00 | Click mic: "My name is Rahul." Then: "What is my name?" | "Conversation memory is per session: it remembers Rahul." |
| 1:25 | Click **New conversation**, ask "What is my name?" | "A new conversation is a new session, so it does not know. Sessions never mix." |
| 1:45 | Switch to **हिन्दी**, ask "भारत की राजधानी क्या है?" | "Hindi works end to end: Whisper in Hindi, the LLM replying in Devanagari, and a Hindi Kokoro voice." |
| 2:05 | Start a long question, then click the mic again mid-answer. | "Starting a new recording interrupts the old answer, and a late reply is discarded rather than spoken." |
| 2:20 | Stop the backend's Ollama (or unplug) and ask a question. Show the error. Restart. | "When a model is down you get a clear message, never a made-up answer." |
| 2:35 | Open README / `docs/architecture.md`, run `pytest` summary. | "Architecture diagram, automated tests, and a benchmark script for measuring cold and warm latency." |

Tip: rehearse the Hindi turn first; Qwen2.5-3B is weaker in Hindi than English, so choose simple questions.
