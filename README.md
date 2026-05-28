# LogaVision

LogaVision is a series of algorithmic stock scanners built with Python and OpenCV designed to automate my manual charting logic. It identifies high-probability technical setups and sends them to Discord Webhooks to optimize efficiency and minimize missed opportunities

## Core Architecture

The system is divided into 2 main scanners: One optimized for swing trading, and the other optimizefor intraday day trading. Both are powered by computer vision

### The Mass Scanner
An object oriented scanner to process custom watchlists of tickers
* **Market Breadth**: Calculates market health through a series of breadth indicators
* **Setups**: Categorizes the chart into a series of setup types, depending on pattern recognition
* **Confluence**: Idenitifies signals to create higher level and strength-based alerts 

### The Day Scanner
A high speed scanner engineered for intraday alerts on a single stock ticker
* **Real-Time**: The system is designed to run in real-time, allowing for enhanced trading
* **Setups**: Identifies high-probability setups using a series of indicators and algorithms
* **Confluence**: Identifies overlapping signals to create a higher-probability alert

### The Vision Engine
To prevent API limitations, LogaVision uses Playwright to automatically open and capture my TradingView chart and indicators

## Note to Reviewers
To protect the project, exact numerical values and risk thresholds are abstracted from this repository
The codebase is public primarily to demonstrate the computer vision architecture and display the project
If you wish to clone and run the structural shell of this project, you must create a 'config.py' file in the root directory and authenticate your TradingView session via the user configuration script
