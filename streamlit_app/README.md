# Steam Games Analytics Dashboard

An interactive Streamlit dashboard that replicates the analyses from the original Jupyter notebook (`project2 (2).ipynb`) with interactive widgets and visualizations.

## Overview

This dashboard separates the Steam catalog experience from analytical views:
- **Game Listing** - Product-style game cards with detail pages, reviews, search, filters, sorting, and pagination
- **Analytics** - A separate page containing overview, tag, profit, genre, release, language, DLC, and ML analysis types

## Getting Started

### Prerequisites

- Python 3.8+
- pip package manager

### Installation

1. **Clone or download** this repository

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install streamlit pandas numpy plotly pymongo dnspython scikit-learn matplotlib seaborn
```

3. **Configure MongoDB**:
   - The app reads MongoDB settings from `MONGODB_URI`, `.streamlit/secrets.toml`, or `~/.streamlit/secrets.toml`
   - Optional collection overrides: `MONGODB_DATABASE`, `MONGODB_GAMES_COLLECTION`, `MONGODB_DLCS_COLLECTION`, `MONGODB_REVIEWS_COLLECTION`, `MONGODB_GAME_EXTRA_COLLECTION`
   - If collection names are blank, the app auto-detects likely games, DLC, reviews, and game extra collections

### Running the Dashboard

From the repository root:
```bash
streamlit run streamlit_app/app.py
```

From inside `streamlit_app/`:
```bash
streamlit run app.py
```

The dashboard will open automatically in your default web browser at `http://localhost:8501`.

## Data Source

Data is loaded from MongoDB Atlas at startup and cached for 10 minutes.

1. **Games collection** (Required) - Main games dataset
2. **DLCs collection** (Optional) - Enables DLC impact analysis
3. **Reviews collection** (Optional) - Enables ML models and review-derived sections
4. **Game_extra_Data collection** (Optional) - Adds user-defined tags to product detail pages

Data is cached for faster reloads and refreshes automatically after the cache expires.

## File Structure

```
streamlit_app/
|-- app.py                    # Small Streamlit entrypoint and page router
|-- data_processing.py        # Data loading, preprocessing, and dataframe summaries
|-- ui.py                     # Sidebar, CSS, and shared Streamlit UI helpers
|-- .streamlit/
|   `-- secrets.toml          # Local MongoDB connection settings
|-- sections/                 # Game listing plus analytics render modules
|   |-- analytics.py
|   |-- game_listing.py
|   |-- overview.py
|   |-- tag_analysis.py
|   |-- profit_analysis.py
|   |-- genre_analysis.py
|   |-- release_trends.py
|   |-- language_categories.py
|   |-- dlc_impact.py
|   `-- ml_model_trainer.py
|-- requirements.txt          # Python dependencies
|-- README.md                 # This file
`-- data/                     # Optional local data folder
```

## Features

### Interactive Controls
- **Game Catalog Filters** - Search, genre, tag, category, price, release year, score, and DLC filters
- **Tag Count Slider** - Control the number of tags displayed
- **Chart Type Selector** - Switch between bar charts, treemaps, and scatter plots
- **Sort Options** - Sort profit analysis by different metrics
- **Feature Selection** - Choose features for ML model training
- **Test Size Slider** - Adjust train/test split ratio

### Visualizations
- Interactive Plotly charts with hover tooltips
- Heatmaps for tag statistics
- Confusion matrices for ML models
- Feature importance plots for tree-based models
- Quadrant analysis for competition vs profitability

## App Pages

### 1. Game Listing
- Product-style cards for browsing the Steam game catalog
- Internal product details pages for individual games
- DLC list inside each product detail page when DLC records are available
- DLC detail pages clearly labeled as DLC/add-on content
- User-defined tags from `Game_extra_Data` merged into PDP tag chips
- Game review cards with recommendation filters and review-text search
- Search by title, description, developer, or publisher
- Filter by genre, tag, category, price range, release year, positive review percentage, and DLC availability
- Sort by reviews, score, release date, price, or name

### 2. Analytics
- A separate analytics page with an analytics type selector
- Includes the dashboard analysis views listed below

## Analytics Types

### Overview & Summary
- Total games count
- Average price and review metrics
- Price and review distribution histograms
- Missing values analysis

### Tag Analysis
- Most common game tags
- Positive vs negative reviews by tag
- Tag statistics heatmap
- Tag counts with interactive filtering

### Profit Analysis
- Estimated profit by tag (40% revenue share assumption)
- Average profit per game by tag
- Top games by estimated profit
- Profit vs review sentiment scatter plot

### Genre Analysis
- Genre distribution
- Average positive review percentage by genre
- Genre profitability metrics
- Price vs reviews by genre

### Release Trends
- Games released per year
- Average price over years
- Total reviews per year

### Languages & Categories
- Top 15 most used languages
- Top 10 game categories/features

### DLC Impact
- DLCs vs positive reviews correlation
- Summary statistics by DLC count

### ML Model Trainer
- KNN, Gaussian Naive Bayes, Random Forest, Decision Tree
- Interactive feature selection
- Confusion matrix visualization
- Feature importance for tree-based models
- Model comparison summary

## Profit Calculation

Profit is estimated using the following formula:
```
Profit = Price * Total Reviews * 0.4
```

`total_reviews` is used as the purchase estimate. The `0.4` multiplier represents Steam's approximate 40% revenue share.

## Troubleshooting

### Dashboard doesn't open
- Check if port 8501 is available
- Try: `streamlit run streamlit_app/app.py --server.port 8502`

### Data not loading
- Ensure Atlas Network Access allows this machine's current public IP address
- For `SSL handshake failed: tlsv1 alert internal error`, add the displayed IP as `/32` in Atlas: **Security > Network Access > Add IP Address**
- Ensure `.streamlit/secrets.toml`, `~/.streamlit/secrets.toml`, or `MONGODB_URI` contains a valid URI
- Set collection names explicitly if auto-detection picks the wrong database or collection

### ML models not training
- Ensure the reviews collection is available in MongoDB
- Ensure the reviews data contains required columns

## Notes

- The dashboard replicates all analyses from the original notebook
- All visualizations are interactive - hover over charts for details
- Data is cached for faster subsequent loads
- The dashboard works best with larger datasets (1000+ records)

## Contributing

Feel free to submit issues and pull requests!

## License

This project is for educational and analytical purposes.
