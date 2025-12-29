## Questify - Question Paper Generator

Build question papers from a syllabus PDF using Streamlit, an LLM (OpenAI-compatible or Ollama), and SQLite. Questions are stored for reuse and can be exported as PDF or Word.

### Features
- Upload syllabus PDF, auto-parse into units
- Generate 4 questions per unit via LLM (2 x 4M, 2 x 6M)
- Store questions in SQLite with unit, marks, difficulty
- Filter by units, marks, difficulty; pick questions to reach total marks
- Export as PDF (ReportLab) or Word (python-docx)

### Project Structure
- `app.py`: Streamlit UI and orchestration
- `database.py`: SQLite schema and CRUD helpers
- `llm_utils.py`: PDF parsing and LLM calls (OpenAI/Ollama)
- `pdf_generator.py`: PDF/Word generation + sample syllabus PDF generator
- `requirements.txt`: Python dependencies

### Setup
1) Python 3.10+
2) Install dependencies:
```bash
pip install -r requirements.txt
```

### LLM Backends
Choose one of the following:

- OpenAI-compatible (OpenAI or any v1-compatible provider):
  - Set environment variables:
```bash
$env:OPENAI_API_KEY = "sk-..."   # PowerShell on Windows
# Optional: custom endpoint/model
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:OPENAI_MODEL = "gpt-4o-mini"
```

- Ollama (local LLaMA):
  - Install and run Ollama, pull a model (e.g., llama3.1)
```bash
ollama pull llama3.1
# Optional environment variables
$env:OLLAMA_MODEL = "llama3.1"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
```

### Run
```bash
streamlit run app.py
```

Open the app in your browser. Use the sidebar to download a sample syllabus PDF if you need one, upload your syllabus, generate questions, and create the paper.

### Notes
- Database file defaults to `questify.db`. Override with `QUESTIFY_DB_PATH` env var.
- Syllabus parsing is heuristic; headings like "Unit 1", "Module 2" improve accuracy.

