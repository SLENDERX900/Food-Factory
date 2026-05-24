# Food Factory

A Streamlit-powered multi-platform marketing workspace. The current toolset includes Pinterest production workflows and Reddit research so you can scrape recipes, generate hooks, schedule pins, sync with Notion, and study community language in one place.

## Features

- **Pinterest Studio**: Automatically scrape recipes from your food blog website or manually enter recipe data
- **Reddit Radar**: Scrape relevant Reddit posts to capture audience language and discussion themes
- **Scheduler Hub**: Queue Pinterest and Reddit content with a shared publishing workflow

**Live Demo**: https://pinterest-factory-example.streamlit.app/

> **Try it out**: The live demo is fully functional! You can scrape recipes from any food blog and generate AI copy instantly.
>
> **Setup required**: Add your `GROQ_API_KEY` to Streamlit Cloud secrets for AI generation (get free credits at https://console.groq.com/keys)
>
> **Note**: Notion sync requires your own Notion API token. All other features work out of the box.

- **AI Copy Engine**: Generate multiple hook angles and compelling descriptions using Groq API (fast cloud LLM)

- **Pin Generation**: Create visually appealing pins with custom typography and layout

- **Notion Sync**: Export generated content to Notion database for content management

## Tech Stack

- **Frontend**: Streamlit (web interface)
- **AI**: Groq API (cloud LLM with free tier)
- **Web Scraping**: ultimate-sitemap-parser, recipe-scrapers (600+ sites supported)
- **Image Processing**: Pillow (PIL)
- **Data**: Pandas
- **Environment**: python-dotenv

## Project Structure

```
Pinterest-Factory/
|
app.py                    # Main Streamlit application router
components/               # Tab components
  |-- intake.py          # Step 1: Batch recipe intake
  |-- ai_engine.py       # Step 2: AI copy generation
  |-- pin_generator.py   # Step 3: Visual pin creation
  |-- notion_sync.py     # Step 4: Notion database sync
  |-- export.py          # Export utilities
utils/                   # Helper utilities
  |-- web_scraper.py     # Web scraping with sitemap support
  |-- groq_client.py     # Groq API client for AI generation
requirements.txt         # Python dependencies
.env.example            # Environment variables template
template.png            # Pin design template
Montserrat/             # Font files for pin design
```

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/Pinterest-Factory.git
   cd Pinterest-Factory
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

5. **Get Groq API Key** (for AI features)
   - Sign up at https://console.groq.com/keys
   - Create a free API key (includes $5 credits)
   - Add to your `.env` file

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```env
# Groq API (required for AI generation - get free credits at https://console.groq.com/keys)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GROQ_MODEL=llama-3.1-8b-instant

# Notion Integration (optional - for Tab 4 sync)
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Notion Setup

1. Create a Notion integration at https://www.notion.so/my-integrations
2. Share your recipe database with the integration
3. Copy the integration token and database ID to your `.env` file

## Usage

1. **Start the application**
   ```bash
   streamlit run app.py
   ```

2. **Navigate through the 4-step workflow:**

   **Step 1: Batch Intake**
   - Enter your food blog URL to automatically scrape recipe information
   - Filter and select recipes for your batch
   - Add custom recipes manually if needed
   - Lock the batch to proceed

   **Step 2: AI Copy Engine**
   - Generate multiple hook angles for each recipe
   - Create compelling descriptions
   - Review and edit AI-generated content

   **Step 3: Pin Generation**
   - Generate visual pins using custom templates
   - Customise typography and layout
   - Export pin images

   **Step 4: Notion Sync**
   - Export all generated content to Notion
   - Track production status
   - Manage content calendar

## Features in Detail

### Recipe Management
- Automatic web scraping from food blog websites
- Intelligent recipe extraction (name, time, ingredients, benefits)
- **Nutrition Facts Extraction**: Automatically extracts calories, protein, carbs, and fat from recipe pages
- Custom recipe entry with URL validation
- Benefit categorization (Quick Weeknight, High Protein, Budget Friendly, etc.)
- Batch locking to prevent accidental changes

### AI-Powered Copy Generation
- Multiple hook angles per recipe (5-7 variations)
- Compelling descriptions optimised for Pinterest
- Groq API integration for fast, high-quality generation
- Customizable prompts and parameters

### Visual Pin Design
- Custom template system
- Montserrat font family for professional typography
- Responsive layout generation
- Batch export capabilities

### Content Management
- Notion database synchronization
- Production status tracking
- Export to CSV format
- Content calendar integration

## Development

### Web Scraping Features
The app automatically extracts recipe information from food blog websites:
- **Recipe Detection**: Finds recipe links using common URL patterns
- **Data Extraction**: Extracts recipe names, cooking times, ingredient counts, benefits, and **nutrition facts**
- **Smart Categorization**: Automatically categorizes recipes based on content analysis
- **Respectful Scraping**: Includes rate limiting to avoid overwhelming servers
- **Nutrition Intelligence**: Estimates calories when data not available and highlights key nutritional information

### Manual Recipe Entry
You can still add recipes manually if web scraping doesn't find all your content:

```python
# Manual entry format (for reference)
{"name": "Recipe Name", "url": "https://yourwebsite.com/recipe-slug", "time": "XX mins", "ingredients": "X", "benefit": "Category"},
```

### Nutrition Facts Display
When recipes are scraped, the app automatically:
- Extracts calories, protein, carbohydrates, and fat from structured data
- Shows nutrition metrics in a clean, organized format
- Generates highlights based on nutritional content (low calorie, high protein, etc.)
- Provides estimates when exact nutrition data isn't available

### Customising Pin Templates
Replace `template.png` with your own design template. The system automatically overlays text based on the template dimensions.

### Extending AI Prompts
Modify the prompt templates in `components/ai_engine.py` to customise the generated content style and tone.

## Troubleshooting

### AI Generation Issues
- Verify your `GROQ_API_KEY` is set correctly in `.env`
- Check that you have credits at https://console.groq.com/keys
- The app uses `llama-3.1-8b-instant` model by default

### Notion Sync Problems
- Verify integration token is valid
- Ensure databases is shared with the integration
- Check database ID matches the correct database

### Font Rendering Issues
- Ensure Montserrat font files are in the `/Montserrat` directory
- Verify font permissions and file integrity

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Deployment

### Streamlit Cloud (Recommended)
1. Push your code to GitHub
2. Connect your repository to Streamlit Cloud
3. Configure environment variables in Streamlit Cloud dashboard
4. Deploy - your app will be live at `https://yourapp.streamlit.app`

### Other Platforms
- **Heroku**: Use the Streamlit Heroku template
- **Render**: Deploy as a web service
- **DigitalOcean**: Use App Platform
- **Self-hosting**: Run on any server with `streamlit run app.py`

## Support

For issues and questions:
- Create an issue on GitHub
- Check the troubleshooting section above
- Review Streamlit documentation for deployment guidance

---

**Food Factory** - Building repeatable marketing workflows across Pinterest, Reddit, and the next channels you add.
