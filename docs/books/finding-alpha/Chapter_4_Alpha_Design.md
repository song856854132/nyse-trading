4
Alpha Design
By Scott Bender and Yongfeng He
This chapter will lay out the process of designing an alpha, starting with raw data. We will discuss some of the important design decisions you need to make when creating an alpha, as well as how to properly evaluate an alpha. At the end of this chapter, we will highlight some issues that can arise after alphas have been developed and put into production.
DATA INPUTS TO AN ALPHA
Alphas are fueled by data. The edge sought for an alpha may come from identifying high-quality pieces of publicly available data, superior processing of the data – or both.
Some typical data sources are:
• Prices and volumes. Technical analysis or regression models may be built based on this data.
• Fundamentals. By automating the analysis of key metrics for each company, you can build alphas that typically have very low turnover.
• Macroeconomic data, such as GDP numbers and employment rates, that have market-wide effects upon their release.
• Text, such as Federal Open Market Committee minutes, company filings, papers, journals, news, or social media.
• Multimedia, notably relevant videos or audio. There are mature techniques to process such data – for example, converting audio into text that can be used to build models.
Sometimes data sources aren't used to generate a directional signal but to attempt to reduce noise in predictions and refine other alpha signals. Examples are:
• Risk factor models. By controlling risk exposure or eliminating exposure to some risk factors, one can seek to improve the alpha's performance.
• Relationship models, such as instruments that typically are correlated with each other to some extent. Some may lead or lag others, thus generating potential opportunities for arbitrage.
Today, with information growing explosively, extracting signals from an expanding ocean of data is more and more challenging. The solution space is nonconvex, discontinuous, and dynamic; good signals often arise where they are least expected. How can we extract such signals? By limiting the search space and using methods previously employed by treasure hunters:
• Searching in the vicinity of previous discoveries.
• Conserving resources to avoid digging too deeply.
• Using validated cues to improve the probability of a find.
• Allocating at least some resources (computational power) to test wild theories.
ALPHA UNIVERSE
An important step in designing an alpha is choosing the target set of assets to be traded; this set of assets is called the universe of the alpha. The universe may be restricted along one or more dimensions, such as:
• Asset class (stocks, exchange-traded funds, futures, currencies, options, bonds, etc.)
• Region or country
• Sector or industry
• Individual instruments
The universe choice typically is driven by the coverage of the input data or the alpha idea, but alphas can be designed and tuned specifically for a certain universe even if the data has wider coverage.
ALPHA PREDICTION FREQUENCY
Another important design decision when creating an alpha is
the prediction frequency. This defines the times at which the alpha will generate new predictions.
Some typical frequencies:
• Tick. New predictions are triggered by events such as a trade in the market.
• Intraday. Predictions are generated multiple times at predetermined points during the day.
• Daily. One prediction per day, of which there are several typical subtypes:
    • Delay 1. Only data available before the current trading day may be used to make a prediction.
    • Delay 0 snapshot. Data before a specific time may be used to make a prediction.
    • MOO/MOC. Predictions are tied to the opening or closing auction.
• Weekly or monthly.
As with the choice of universe, this decision often is guided by the frequency of the input data.
VALUE OF AN ALPHA
The ultimate test of alpha value is how much risk-adjusted profit the alpha adds to the strategy in which it is trading. In practice, this is difficult to precisely measure because:
• There is no canonical strategy in which an alpha may be used, and the exact strategy in which the alpha will be used may not be known at the time of its design.
• There are often nonlinear effects in the combination that make it difficult to precisely attribute profit to individual alphas.
All that said, we can still make useful predictions about whether an alpha will add value in strategies, and we can provide a reasonable estimate of how much an alpha contributed to the strategy's performance.
PRACTICAL ALPHA EVALUATION
Because the target trading strategy may not be known when the alpha is being designed, when considering an alpha on its own, how can we know if it will be useful? Alternatively, when an alpha is changed, is it really improved? To answer these questions, good quantitative measurements are required.
A typical method for collecting measurements about trading strategies is to run a simulation (that is, backtest) and measure characteristics of the result, such as the information ratio. One way to make analogous measurements for an alpha is to do a mapping of its predictions to a trading strategy and then run such a simulation. There are different ways to do this mapping, but the simplest is to assume the prediction strength of an alpha is the dollar position taken by the trading strategy. One issue with this mapping method is that alphas often will not map to good strategies on their own because they are designed to predict returns, not to make profitable trades net of costs. One way to address this issue is by charging reduced transaction costs in the simulation.
Once the simulation has been constructed, some useful measurements that can be taken are:
• Information ratio. The mean of the alpha's returns divided by the standard deviation of the returns, this measures how consistently the alpha makes good predictions. Combining the information ratio with the length of the observation period can help us determine our level of confidence that the alpha is better than random noise. A reasonable annualized information ratio for a unique alpha with little fitting, observed over a five-year period, would be 1.0. In practice, alphas have some fitting and some correlation to existing alphas, so the information ratio is typically a bit higher than this.
• Margin is the amount of profit the alpha made in the
simulation divided by the amount of trading that was done. This is an indicator of how sensitive the alpha is to transaction costs. A higher margin means the alpha is not much affected by trading costs. Alphas with low margins won't add value unless they are very different from the other alphas in the strategy. For an average daily alpha, a margin of 5 basis points typically is acceptable.
• Correlation measures the uniqueness of an alpha and often is measured against the most correlated alpha that exists in the alpha pool. Lower correlation indicates that the alpha is more unique and therefore more desirable. For an alpha whose characteristics are otherwise average, the following interpretation of the maximum correlation is reasonable:
    • More than 0.7: Too high unless the alpha is significantly better than the existing alpha.
    • 0.5 to 0.7: Borderline. The alpha should be exceptional in some other metric.
    • 0.3 to 0.5: Generally acceptable.
    • Less than 0.3: Good.
The measurements above can be made more complex. For example, it can be useful to test whether the alpha has good information ratios on both liquid stocks (stocks with high trading volume) and illiquid stocks. If the alpha is only predictive on illiquid stocks, it may have limited usefulness in a strategy that intends to trade very large sizes.
FUTURE PERFORMANCE
All of the measurements in the preceding section are intended to evaluate an alpha when there is no information other than the actual predictions. However, additional information, such as how the alpha was constructed, can be useful in determining whether the alpha will make good predictions going forward. Ultimately, what is important is whether the alpha makes usable future predictions, not historical predictions.
Consider an alpha that has a high information ratio but was built by optimizing parameters that have no economic explanation to historical data. For example, suppose the alpha had 12 parameters, one for each month (x1…x12), and suppose the alpha rule is simply to buy x1 dollars of all stocks in January, x2 dollars of all stocks in February, and so forth. If x1–x12 was optimized over the past year, the alpha would make good predictions for the past year, but there is no reason to think they would work going into the next year.
In general, each optimization or improvement made to an alpha after observing historical data will improve the alpha's historical performance by some amount and its future performance by some different, usually smaller, amount. The alpha designer should take special care to ensure that changes are expected to improve the alpha going forward, not just historically.
When changes to the alpha yield very small (or even negative) improvements to the future predictions compared with large improvements of historical predictions, the alpha is being overfit to the historical data. Alpha designers can measure the effect of this overfitting by looking at the performance of their alphas on data that was not used in alpha construction (out-of-sample data) and comparing it with the data used to improve the alpha (in-sample data). The comparison of in-sample to out-of-sample performance is useful not only on the alpha level but also in aggregate across all alphas from a given designer or on groups of alphas from a given designer. These comparisons on groups of alphas can measure the tendency of a designer's methodology to overfit.
CONCLUSION
This chapter discussed the major elements of alpha design,
including practical approaches to evaluate alphas. Some potential issues that arise after alphas are developed also were addressed. By harnessing the exponential growth of computing power and data sources, combined with a solid alpha design framework, we can generate alphas and trading strategies that evolve with the market.
