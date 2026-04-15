5
How to Develop an Alpha: A Case Study
By Pankaj Bakliwal and and Hongzhi Chen
In this chapter, we explain how to design an alpha, the logic behind an alpha, how to convert an alpha idea into a mathematical predictive formula by using appropriate information, and how to improve the idea. We will also introduce some important concepts on evaluating the performance of an alpha.
Before we talk more about alpha development and design, let's study a simple example to get a better understanding of what an alpha looks like.
Let's say we have $1 million in capital and want to invest continuously in a portfolio consisting of two stocks: Alphabet (GOOG) and Apple (AAPL). We need to know how to allocate our capital between these two stocks. If we do a daily rebalancing of our portfolio, we need to predict the next few days' return of each stock. How do we do this?
There are a lot of things that can affect the stocks' prices, such as trader behavior, price trends, news, fundamental corporate change, and a change in holdings by big institutions or corporate insiders – officers, directors, or shareholders with more than 10% of a class of the company's registered equity securities. To make things simple, we can deconstruct the prediction process into two steps: first, we predict the stock returns of each instrument, using a single factor like news or price trends; second, we aggregate all the different predictions.
Let's try to develop an alpha using recent price trends, employing available data in the form of the daily historical prices of these two stocks. The next step is to come up with a sensible idea. Let's say that, based on the historical prices, we observe that the two stocks have trended upward during the past week. Logic says that in the absence of any additional information, when stock prices rise, investors tend to book profits and close their long positions, which in turn pushes the stock prices downward. At the same time, when stock prices fall, investors see an opportunity to buy shares at a cheaper rate, which in turn pushes the stock prices upward.
Converting an idea into a mathematical expression is not always straightforward. In the above case, though, it can be done simply as follows:

Alpha = -(1 week returns)

The negative sign indicates that a short position is taken when the trend is upward and a long position when the trend is downward. The dollar amount of the long–short position in a particular financial instrument is determined by the magnitude of the value given by the formula. This means that the stronger the price trend, the greater the likelihood the price will revert. Suppose our algorithm produces the following values for two stocks, respectively:

Alpha(GOOG) = 2
Alpha(AAPL) = -1

The values above have a ratio of 2 to -1. This means we want to hold twice as much of GOOG as we do of AAPL; the positive number means we want to hold a long position, while the negative number means we want to hold a short position. Thus, using $1 million of capital as an example, we want to be long $1 million of GOOG and short $500,000 of AAPL at the end of today's trading. This example, of course, assumes zero transaction costs.
So the alpha model is actually an algorithm that transforms input data (price-volume, news, fundamental, etc.) into a vector, which is proportional to the money we want to hold in each instrument.

Alpha(input data) -> alpha value vector

Now that we understand what an alpha is, let's write our first alpha.1 We will introduce more concepts along the way.
Above all, we need to define a universe – that is, the set of financial instruments on which we want to build the alpha model. Let's focus on the US equity market. There are different ways to select equity instruments, such as using components of the S&P 500 index. Suppose we use the most liquid 3,000 stocks in the US as our research universe (call it TOP3000).
Next we need an idea to predict the stock price. We can use the same mean-reversion idea mentioned above and express it in terms of a mathematical expression as follows:

Alpha1 = -(close(today) - close(5_days_ago)) / close(5_days_ago)

To find out if this idea works, we need a simulator to do backtesting. We can use WebSim for this purpose.
Using WebSim, we get the sample results for this alpha, as shown in Figure 5.1.
[Graph: Cumulative profit]
Figure 5.1 Sample simulation result of Alpha1 by WebSim
Table 5.1 shows several performance metrics used to evaluate an alpha. We focus on the most important metrics.
Table 5.1 Evaluation of Alpha1 simulation graph
Note: Provided for illustrative purposes only.
Year Book size PnL Ann.return Information ratio Max drawdown % profitable days Daily turnover Profit per $ traded
2010 2.0E7 4.27E6 46.44% 1.32 16.63% 46.52% 62.69% 0.15¢
2011 2.0E7 6.93E6 68.70% 1.42 39.22% 50.79% 64.72% 0.21¢
2012 2.0E7 2.01E6 20.08% 0.96 14.66% 51.20% 63.36% 0.06¢
2013 2.0E7 1.04E6 10.34% 0.60 9.22% 46.83% 63.26% 0.03¢
2014 2.0E7 1.48E6 14.72% 0.61 28.67% 51.19% 62.36% 0.05¢
2015 2.0E7 -158.21E3 -32.96% -1.38 4.65% 41.67% 64.34% -0.10¢
2010-15 2.0E7 15.57E6 31.20% 1.00 39.22% 49.28% 63.30% 0.10¢

The backtesting is done from 2010 through 2015, so each row of the output lists the annual performance of that year. The total simulation book size is always fixed at $20 million; the PnL is the annual PnL.
Annual return is defined as:

Ann_return = ann_pnl / (booksize / 2)

The annual return measures the profitability of the alpha.
The information ratio is the single most important metric we will look at. It is defined as:

Information_ratio = (average daily return) / (daily volatility) * sqrt(256)

The information ratio measures the information contained in the alpha, which roughly means the stability of the alpha's profitability: higher is better.
Max drawdown measures the highest peak-to-trough loss from a local maximum of the PnL to a subsequent local minimum as a percentage of book size divided by two (the long or short side of the book).
Percent profitable days measures the percentage of positive days in each year.
Daily turnover measures how fast you rebalance your portfolio and is defined as:

Daily_turnover = (average dollars traded each day) / booksize

Profit per dollar traded measures how much you made for each dollar you traded and is defined as:

Profit_per_$_traded = pnl / total_traded_dollar

For this alpha, the total information ratio is about 1, with a high return of about 31.2% but with a very high max drawdown of 39.22%. This means the risk is very high, so the PnL is not very stable. To reduce the simulated max drawdown, we need to remove some potential risks. We can achieve this by using some risk neutralization techniques. Industry risk and market risk are the biggest risks for the equity market. We can partially remove them by requiring our portfolios to be long–short balanced within each industry. We neutralize our alpha by requiring:
Sum(Alpha2 value within same industry) = 0

By doing this, we get a new sample result, as seen in Figure 5.2.
[Graph: Cumulative profit]
Figure 5.2 Sample simulation result of Alpha2 by WebSim
As Table 5.2 shows, the information ratio is increased to 1.37 and the return is decreased to 10.22%, but the max drawdown is decreased significantly, to less than 9%. This is a big improvement.

Table 5.2 Evaluation of Alpha2 simulation graph
Year Book size PnL Ann.return Information ratio Max drawdown % profitable days Daily turnover Profit per $ traded
2010 2.0E7 1.59E6 17.30% 2.44 5.44% 51.30% 63.73% 0.05¢
2011 2.0E7 1.66E6 16.50% 1.81 5.27% 49.21% 63.85% 0.05¢
2012 2.0E7 518.24E3 5.18% 0.90 6.66% 55.20% 63.12% 0.02¢
2013 2.0E7 450.88E3 4.47% 0.80 4.97% 51.59% 62.99% 0.01¢
2014 2.0E7 1.11E6 11.02% 1.24 8.73% 53.17% 62.86% 0.04¢
2015 2.0E7 -231.40E3 -48.21% -5.96 2.88% 33.33% 62.30% -0.15¢
2010-15 2.0E7 5.10E6 10.22% 1.37 8.73% 51.92% 63.29% 0.03¢

The magnitude of our alpha is five days' return, which is not very accurate as a predictor; the relative size may be more accurate. To improve the alpha, we introduce the concept of cross-sectional rank, which means using the relative rank of the alpha values as the new alpha values.

Alpha3 = rank(Alpha1)

Sum(Alpha3 value within same industry) = 0

The results are reflected in Figure 5.3.
[Graph: Cumulative profit]
Figure 5.3 Sample simulation result of Alpha3 by WebSim
As can be seen from Table 5.3, we get another significant improvement. Now the performance looks much better, but the turnover is still a little high. We can try to decrease it by using decay. Decay means averaging your alpha signal over some time window.

Table 5.3 Evaluation of Alpha3 simulation result
Year Book size PnL Ann.return Information ratio Max drawdown % profitable days Daily turnover Profit per $ traded
2010 2.0E7 1.83E6 19.94% 3.43 3.11% 56.52% 59.43% 0.07¢
2011 2.0E7 1.34E6 13.30% 1.70 5.82% 53.17% 59.49% 0.04¢
2012 2.0E7 801.74E3 8.02% 1.89 1.93% 55.20% 58.94% 0.03¢
2013 2.0E7 692.73E3 6.87% 1.94 2.49% 53.57% 58.69% 0.02¢
2014 2.0E7 518.06E3 5.14% 0.93 5.43% 52.38% 59.20% 0.02¢
2015 2.0E7 -251.40E3 -52.37% -10.45 2.78% 33.33% 59.59% -0.18¢
2010-15 2.0E7 4.94E6 9.89% 1.76 5.82% 53.93% 59.15% 0.03¢

Basically, it means:

New_alpha = new_alpha + weighted_old_alpha

When we try three days' decay in WebSim, we get the results shown in Figure 5.4.
[Graph: Cumulative profit]
Figure 5.4 Sample simulation result of New_alpha by WebSim
Table 5.4 looks great. Not only is the turnover decreased, but the information ratio, return, and drawdown are also improved. Note that at each point, after evaluating the performance of the alpha, you can go back to the raw idea and make meaningful changes to further improve the alpha.

Table 5.4 Evaluation of New_alpha simulation result
Year Book size PnL Ann.return Information ratio Max drawdown % profitable days Daily turnover Profit per $ traded
2010 2.0E7 1.72E6 18.66% 3.09 4.11% 53.91% 42.48% 0.09¢
2011 2.0E7 1.61E6 15.94% 2.01 4.87% 51.19% 42.28% 0.08¢
2012 2.0E7 814.03E3 8.14% 1.90 2.05% 57.20% 42.09% 0.04¢
2013 2.0E7 643.29E3 6.38% 1.88 2.48% 54.76% 41.87% 0.03¢
2014 2.0E7 599.21E3 5.94% 1.03 7.74% 51.59% 42.09% 0.03¢
2015 2.0E7 -194.34E3 -40.49% -7.20 2.58% 33.33% 41.82% -0.19¢
2010-15 2.0E7 5.19E6 10.39% 1.82 7.74% 53.53% 42.15% 0.05¢

CONCLUSION
In this chapter, we have explained the logic behind an alpha, provided some examples of ideas, and discussed how to convert those ideas into mathematical expressions and translate them into instrument positions. We have also explained how to analyze and improve an alpha's performance. The entire alpha logic is nicely summarized by the flow chart in Figure 5.5.
[Graph: Figure 5.5 Five steps to creating alphas (Idea -> Raw alpha -> Position -> PnL -> Performance)]
Figure 5.5 Five steps to creating alphas
You can think of more ways to improve an alpha – just be creative.
The next step is to explore other ideas and datasets, hunting for something really unique. A unique idea is good because you can trade it before others do, potentially leading to more profit.
Good luck!
NOTE
1 The sample alphas and returns described in this chapter are included for illustrative purposes only and are not intended to be indicative of any strategy utilized by WorldQuant or its affiliates.
