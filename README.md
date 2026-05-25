# LogaVision

LogaVision is a series of algorithmic stock scanners built with Python and OpenCV designed to automate my mnaual charting logic. It identifies high-probability technical setups and streams them to Discord Webhooks to optimize efficiency and minimize missed opportunities

## Core Architecture

The vision is divided into 2 main scanners: One for swing trading, and one for day trading, both powered by computer vision

### The Mass Scanner
An object oriented scanner to process custom watchlists of tickers
* **Market Breadth**: Calculates market health through a series of breadth indicators
* **Setups**: Categorizes the chart into a series of setup types, depending on 
* **Confluence**: Idenitifies signals to create higher level and strength-based alerts 

### The Day Scanner
A high speed scanner engineered for intraday alerts
* **Real-Time**: The system is designed to run in real-time, allowing for enhanced work
* **Setups**: Identifies a series of indicators and algorithms to create high-probability setups
* **Confluence**: Identifies overlapping signals to create a stronger alert

### The Vision Engine
To prevent API limitations, LogaVision uses playwright to automatically open and capture my tradingview chart and indicators

## Note to Reviewers
To protect the code, exact numbers used are abstracted from this repository
The public codebase demonstrates the structural engineering, computer vision logic, and state management.
If you wish to clone and run the structural shell of this project, you must create a 'config.py' file in the root directory, in addition to allowing the code to automatically sign you in to TradingView via cookies
