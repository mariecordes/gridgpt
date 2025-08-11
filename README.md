# GridGPT

A smart mini crossword generator powered by GPT that creates themed crossword puzzles with AI-generated clues. GridGPT combines intelligent word placement algorithms with natural language processing to generate engaging crossword puzzles.

## Features

- 🧩 **Smart Grid Generation**: Creates crossword grids using various templates and patterns
- 🎯 **Theme-Based Puzzles**: Generates crosswords around specific themes or topics
- 🤖 **AI-Powered Clues**: Uses GPT to create creative and contextual clues
- 🎨 **Visual Interface**: Modern React frontend with interactive grid previews
- 📊 **Word Database**: Comprehensive database with frequency analysis and filtering

## Architecture

The project consists of three main components:

### Backend (Python/FastAPI)
- **Core engine**: Word placement optimization algorithm and grid generation
- **AI integration**: OpenAI GPT integration for clue generation
- **Database management**: Word database with filtering and frequency analysis
- **API server**: FastAPI endpoints for crossword generation

### Frontend (Next.js/React)
- **Modern UI**: Clean interface built with Next.js and Tailwind CSS
- **Interactive components**: Customization components and visual grid previews and checks
- **Real-time generation**: Live crossword creation with theme selection

### Data Pipeline
- **Web Scraping**: Automated collection of crossword data
- **Data Processing**: Word frequency analysis and clue filtering
- **Template Management**: Grid pattern definitions and configurations

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- OpenAI API key

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/mariecordes/gridgpt.git
   cd gridgpt
   ```

2. **Set up the backend**
   ```bash
   # Create and activate a virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install the package in editable mode with all dependencies
   pip install -e .
   ```

3. **Configure environment**
   ```bash
   cp .env.sample .env

   # Add your OpenAI Azure endpoint and API key to .env

   source .env
   ```

4. **Set up the frontend**
   ```bash
   cd frontend
   npm install
   ```

### Running the Application

1. **Start the backend API**
   ```bash
   python run_api.py
   ```

2. **Start the frontend** (in a new terminal)
   ```bash
   cd frontend
   npm run dev
   ```

3. **Access the application**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## Word Database Setup

GridGPT uses a word database built from online crossword sources. Follow these steps to create and maintain the database:

### 1. Scrape Source Data

**Scrape NYT's Mini Crosswords from worddb.com**
```bash
python scripts/scrape_worddb.py --start-date 2023-01-01 --end-date 2023-12-31
```
This creates and updates: `data/01_raw/worddb_com/nyt_mini_clues.json`


### 2. Process Raw Data

**Create the main word database**
```bash
python scripts/create_worddb_database.py
```
This processes the scraped data and creates: `data/02_intermediary/word_database/word_database_full.json`


### 3. Automatic Filtering

Then whenever `WordDatabaseManager()` is initialized in the backend, it automatically creates an up to date filtered databases relevant for the crossword to be generated:
- `data/02_intermediary/word_database/word_database_filtered.json` - Filtered word-clue pairs
- `data/02_intermediary/word_database/word_list_with_frequencies.json` - Word frequency analysis

The filtering process can flexibly:
- limit for minimum and maximum number of characters in a word
- apply a minimum frequency threshold (e.g., words must have been used in a crossword more than 5 times)
- exclude special characters
- remove reference clues (e.g., "See 15-Across")

### Additional sources

*⚠️ The output of the data pipeline below is currently not in use. In the future, it is planned to integrate this data as well as extend the word database with additional sources.*

**Scrape crossword data from crosswordtracker.com**
```bash
python scripts/scrape_crosswords_2.py letters A B C # list which letter to scrape individually
```
This creates: `data/01_raw/crossword_tracker/crossword_words_[A-Z].json`

**Create crossword tracker database**
```bash
python scripts/create_crosswordtracker_word_db.py
```


## Backend Architecture

### Core Components

-- # TODO: rename CrosswordGenerator to Grid generator & then create a single Crossword generator that takes all inputs from the front end and then outputs the final crossword

generator = CrosswordGenerator() # main orchestrator
result = generator.generate_crossword(theme, template_id, cluetype)

**`CrosswordGenerator`**: Grid generator that fills a crossword template grid with a theme entry under the given constraints.
```python
from src.gridgpt.crossword_generator import CrosswordGenerator

generator = CrosswordGenerator()
result = generator.generate_themed_crossword(template=template_dict, theme_entry="FRUIT")
```

**`WordDatabaseManager`**: Fundamental manager for word database operations
```python
from src.gridgpt.word_database_manager import WordDatabaseManager

db_manager = WordDatabaseManager() # with default values
db_manager = WordDatabaseManager( 
    min_frequency=5,
    min_length=3,
    max_length=5,
    exclude_special_chars=True,
    exclude_reference_clues=True
) # with customized values

# Review available database items
db_manager.word_database_filtered
db_manager.word_list_with_frequencies
```

**`ClueGenerator`**: AI-powered clue creation
```python
from src.gridgpt.clue_manager import ClueGenerator

clue_gen = ClueGenerator()
clue = clue_gen.generate_clue(word="PYTHON", theme="programming")
```

**`ClueRetriever`**: Retrieval of previously published clues
```python
from src.gridgpt.clue_manager import ClueRetriever

clue_retriever = ClueRetriever()

# Identify all listed clues for a word in the database
available_clues = clue_retriever.get_available_clues(word="PYTHON")

# Randomly select a single clue from the database
available_clues = clue_retriever.retrieve_clue(word="PYTHON")
```

**`TemplateManager`**: Grid template management
```python
from src.gridgpt.template_manager import select_template

template = select_template(template_id="5x5_diagonal_cut")
```

### API Endpoints

- `GET /api/templates` - List available grid templates
- `POST /api/generate-crossword` - Generate a complete crossword puzzle
- `POST /api/check-solution` - Check solution against correct answers
- `GET /api/test` - Verify endpoint is working
- `GET /health` - API health check

## Frontend Architecture

### Key Components

**`CrosswordGenerator`**: Main interface component with:
- Template selection with visual preview icons
- Clue type selection (generated vs. retrieved, mandatory)
- Theme input (optional)
- Output crossword grid with interactive fill and solution checks
- Generated/retrieved clue panel


## Development

### Project Structure
```
gridgpt/
├── src/                   # Core Python modules
├── api/                   # FastAPI application
├── frontend/              # Next.js React app
├── data/                  # Word databases and raw data
├── conf/                  # Configuration files
├── scripts/               # Data processing scripts
├── notebooks/             # Jupyter development notebooks
└── tests/                 # Test suites
```

### Adding New Templates

1. **Define the template** in `data/03_templates/grid_templates.json`
2. **Add SVG pattern** to `GridPreview` component
3. **Test generation** with the new template


## Configuration

Configuration files are located in `conf/base/`:

Key configuration files:
- `parameters.yml`: Generation parameters
- `prompts.yml`: AI prompt templates
- `catalog.yml`: List of used data files
- `credentials.yml`: API keys and secrets # TODO: move keys here from .env

## Next steps:

Some of my ideas for future updates and enhancements are:

- Include a difficulty parameter that influences clue generation
- Expand word database sources to include a greater number of words
- Allow inclusion of words that are not listed in the word database (i.e., new entries; potentially with LLM verification)
- Expand templates to different sizes than the plain 5x5 Mini set-up, or even allow flexible user creation of a grid template
- Integrate other LLM providers