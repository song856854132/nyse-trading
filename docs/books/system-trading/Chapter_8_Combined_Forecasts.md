# Chapter Eight. Combined Forecasts

[Image of a matrix: Instruments vs Forecast weights]

## Staunch Systems Trader
This chapter is about combining forecasts from different trading rules, including variations of the same rule, so it's required reading for most staunch systems traders. If you're an asset allocating investor using the single 'no rule' rule or a semi-automatic trader you can skip ahead to chapter nine.

L IFE IS SIMPLE WHEN YOU HAVE ONLY ONE TRADING RULE. Strong positive forecast? Then buy. Negative? Sell. But what if you have multiple rules and they disagree?

As you saw in the previous chapter, in late 2009 and 2010 one of my trading rules (the EWMAC trend following rule) had turned bullish on crude oil, but another (Carry) was still bearish (see figures 18 and 19). What should I have done – buy, sell, or do nothing? Multiple forecasts which disagree aren't conclusive – you need to create a single combined forecast for every instrument.

## Chapter overview

| | |
|---|---|
| Combining with forecast weights | How to use forecast weights to produce a single combined forecast for each instrument. |
| Choosing the forecast weights | Using the handcrafting method to find weights for each trading rule. |
| Getting the correct variation | Making sure the combined forecast has the right expected absolute value by correcting for diversification across the individual forecasts. |
| Capping combined forecasts | Just like the forecast from each trading rule you should limit the size of your combined forecasts. |

## Combining with forecast weights
How do you go from two or more forecasts, to a single combined forecast for each instrument? In the framework you need to use a weighted average of your forecasts, where the weights are forecast weights. These are a type of portfolio weight, where your portfolio consists of trading rule variations, and they should all be positive and add up to 100%.

So if you were trading crude oil in mid-2009, as shown in figures 18 and 19, then you might have had forecasts of +15 in the EWMAC trend following variation and -10 in Carry. With forecast weights of 50% in each rule your combined forecast would be 2.5.86

## Choosing the forecast weights
How do you find the best weights to use when combining forecasts? This is an example of the problem of allocating a portfolio of assets, which we discussed in chapter four. But now the asset weights you have to choose are forecast weights for trading rules and their variations, rather than long positions in equities or bonds.

Forecast weights might be the same for all instruments, or different. I'll now show you how to use the handcrafting method I described in chapter four to find those weights, although you can also use bootstrapping if you're comfortable with that.87 To find handcrafted weights you need both correlations and a way of grouping your assets.

You can back-test the performance of different trading rules to get historical estimates for correlations. Alternatively tables 56 and 57 in appendix C (from page 308) give some typical values for trading rules within the same instrument.

Once you have correlations the next step in the handcrafted method is to group your assets. The simplest way is to group the variations within a particular trading rule, then allocate *across* trading rules. Let's take a simple example. Suppose we're using the two rules from the last chapter, trend following (EWMAC) and Carry. For now assume that EWMAC has three variants, with fast look-backs of 16, 32 and 64 for the moving averages.88 The carry rule has a single variation. Here is how I calculated the weights.

| | |
|---|---|
| First level grouping Within trading rules | • Group one (EWMAC): From table 57 in appendix C (page 309) I get the correlations between EWMAC variations: 0.90 between adjacent variations, and 0.7 between the variations with fast look-backs 16 and 64. Using table 8 (page 89) row 11 I get weights of 16% in look-back 32, and 42% in look-backs 16 and 64.<br>• Group two (Carry): One asset. Using table 8 row 1: 100% in Carry. |
| Second level grouping Across trading rules | Using table 8 row 2: 50% in the EWMAC and 50% in Carry. |

This gives us the weights in table 17. By the way it's also possible to have a three level grouping, if you are mixing rules of different styles.

TABLE 17: EXAMPLE HANDCRAFTED FORECAST WEIGHTS

| | 1st level | 2nd level | Final weights |
|---|---|---|---|
| EWMAC 16, 64 | 42% | 50% | 21% |
| EWMAC 32, 128 | 16% | 50% | 8% |
| EWMAC 64, 256 | 42% | 50% | 21% |
| Carry | 100% | 50% | 50% |

Notice that I haven't shown you how to incorporate different performance between rules, the effect of costs, or how to decide if different instruments should have different weights. If you've followed my advice from chapter three, and not fitted or selected trading rules based on Sharpe ratio, then you risk having some poor rules in your portfolio, on which you could want to reduce the allocation. It's also quite likely faster rules will have worse after-cost performance than slower ones.

I'll discuss these issues in detail in chapter twelve, 'Speed and Size'. There will also be a more realistic example using performance and cost estimates in the staunch systems trader example chapter in part four.

## Getting to 10
I recommended in chapter six that all your individual forecasts should have the same expected variability – equivalent to an expected absolute value of 10. But unless your trading rules are perfectly correlated it's likely that the combined forecast will end up on a smaller scale. It's the same general effect you get from putting less than perfectly correlated assets into any portfolio, where the overall portfolio will always end up with lower risk than its constituents. The magnitude of the fall in standard deviation will depend on the degree of diversification.

However the trading system framework will not work consistently if combined forecasts have a low and unpredictable scaling. You need your combined forecasts to maintain the same expected absolute value of 10 as you required for individual forecasts. To fix this the combined forecast is multiplied by a forecast diversification multiplier.

CONCEPT: DIVERSIFICATION MULTIPLIER
If you have two stocks, each with identical return volatility of 10%, with half your money in each, what will be the volatility of the whole portfolio? Naturally it will depend on how correlated the two assets are.

If they are perfectly correlated then the portfolio will have a return standard deviation of 10%; the same as the individual assets. But if the correlation between the two assets was 0.5, the portfolio volatility would come out at 8.66%.89 Similarly a correlation of zero gives a volatility of 7.07%. More diversified portfolios have lower volatility.

In the framework we are concerned with putting together volatility standardised assets that have the same expected average standard deviation of returns; and to do this we need forecasts to have the same average absolute value. To ensure this is always the case you need to multiply the forecasts or positions you have to account for portfolio diversification, so that your total portfolio also achieves the standard volatility target.

This multiplication factor is the diversification multiplier.90 If the correlation between the two assets in the simple two stocks example is 1.0, then because the portfolio has the same volatility as its members (10%) no adjustment is required, and the multiplier will be 1. A correlation of 0.5 implies a multiplier equal to the target volatility of 10%, divided by the natural portfolio volatility of 8.66%. This will be 10 ÷ 8.66 = 1.15. Finally if the two assets were completely uncorrelated with portfolio volatility of 7.07%, then the multiplier would be 10 ÷ 7.07 = 1.44.

You will get even higher values with negative correlations. However this will result in dangerously large multipliers, so I strongly recommend you floor any estimated correlations at zero.

You can use two possible sources for correlations to do this calculation. Correlations can be estimated with data from back-tests, or using rule of thumb values from the tables in appendix C.91

You can do the actual calculation with the precise equation, or alternatively table 18 gives a rule of thumb which will give a good approximation.92

[Image: 4 graphs showing Forecast rule A, Forecast rule B, Raw combined forecast, Rescaled combined forecast]

FIGURE 20: COMBINING DIFFERENT FORECASTS REDUCES VARIABILITY. RESCALING FIXES THIS

Figure 20 shows this effect for two uncorrelated forecasts A and B, which I've combined with a 50% weight to each. They cover the range from -20 to +20. But the combined forecast is much less variable than I want, with a smaller range of -15 to +12. Scaling the combined forecast up with a forecast diversification multiplier fixes the problem.

TABLE 18: MORE ASSETS AND LOWER CORRELATIONS MEAN MORE DIVERSIFICATION AND A HIGHER MULTIPLIER93

| | Diversification multiplier | | | | |
|---|---|---|---|---|---|
| Number of assets | Average correlation between assets | | | | |
| | 0.0 | 0.25 | 0.5 | 0.75 | 1.0 |
| 2 | 1.41 | 1.27 | 1.15 | 1.10 | 1.0 |
| 3 | 1.73 | 1.41 | 1.22 | 1.12 | 1.0 |
| 4 | 2.0 | 1.51 | 1.27 | 1.10 | 1.0 |
| 5 | 2.2 | 1.58 | 1.29 | 1.15 | 1.0 |
| 10 | 3.2 | 1.75 | 1.35 | 1.17 | 1.0 |
| 15 | 3.9 | 1.83 | 1.37 | 1.17 | 1.0 |
| 20 | 4.5 | 1.86 | 1.38 | 1.18 | 1.0 |
| 50 or more | 7.1 | 1.94 | 1.40 | 1.19 | 1.0 |

The table shows the approximate diversification multiplier given the number of assets in a portfolio (rows) and the average correlation between them (columns). Beware of using very high multipliers.

I'll now explain how to calculate the forecast diversification multiplier. If you don't have back-tested forecast values then you can estimate likely correlations from tables 56 and 57 in appendix C (from page 308). Correlation between selected variations of the same rule tends to be high; up to 0.9 but averaging around 0.7. Across different trading rules within the same style it is around 0.5. Using different styles of rules, correlations for trading rules within an instrument are around 0.25.

For the simple example with four rule variations from earlier in the chapter I populated a correlation matrix using the information in appendix C, which is shown in table 19.

TABLE 19: CORRELATION OF TRADING RULE FORECASTS IN SIMPLE EXAMPLE

| | EW16 | EW32 | EW64 | Carry |
|---|---|---|---|---|
| EWMAC 16,64 | 1 | | | |
| EWMAC 32,128 | 0.9 | 1 | | |
| EWMAC 64,256 | 0.6 | 0.9 | 1 | |
| Carry | 0.25 | 0.25 | 0.25 | 1 |

Values shown are correlations, populated using values in appendix C tables.

You could now use tables 18 and 19 to find an approximate forecast diversification multiplier for the four rule variations. The matrix in table 19 has a rounded average correlation of 0.50,94 which with four assets in table 18 gives a multiplier of 1.27. As a comparison the precise value is 1.31 using the actual forecast weights calculated above and the formula on page 311.

Finally, a word of warning. It's possible, as table 18 shows us, to get very high multipliers if your trading rules are sufficiently diversified, even if you cap negative correlations at zero. As you'll see in a moment I recommend that combined forecasts are limited to a maximum value of 20, so having a high multiplier would mean having capped forecasts most of the time, and effectively behaving as if you had a binary trading rule which is either fully long or fully short.

To avoid this I advocate using a maximum diversification multiplier of 2.5, regardless of what your actual estimate is.

## Capped at 20
In the previous chapter I recommended that you limit the forecast from individual rules to the range -20 to +20. However it's possible in theory for a combined forecast to go above 20 if the forecast diversification multiplier is greater than 1, as is usually the case. To take a simple example, if the Carry rule and a single EWMAC variation both had forecasts of +16, with forecast weights of 50% on each rule, and a diversification multiplier of 1.5, then the combined forecast would be 24.95

All the reasons cited in the previous chapter for limiting individual forecasts apply equally to combined forecasts, so I strongly encourage you to limit combined forecasts to absolute values of 20 or less. Any value outside this range should be capped.

## Summary for combining forecasts

| | |
|---|---|
| Instrument forecasts for each trading rule and variation | You start with the forecasts for each trading rule variation for an instrument. So if you have two rules, each with three variations, then you'd have six possible forecast values per instrument.<br>I recommended in the previous chapter that each individual forecast has an expected average absolute value of around 10 and should be limited to between -20 and +20. |
| Forecast weights | Each rule variation should have a positive forecast weight. The weights must add up to 100%. These weights can be the same across instruments, or different. |
| Raw combined forecast | Using the forecast weights, take a weighted average of the forecasts from each rule variation. |
| Forecast diversification multiplier | This is needed to get the expected absolute value of the combined forecast up to the recommended value of 10.<br>Estimated correlations are needed; from back-test results, or the rule of thumb tables in appendix C. You can then calculate the multiplier approximately from table 18 or precisely using the equation on page 311.<br>The multiplier is at least 1.0 and I recommend a maximum of 2.5. |
| Rescaled combined forecast | This is the raw combined forecast multiplied by the forecast diversification multiplier.<br>Because of the diversification multiplier it will have an expected average absolute value equal to the expected variability of the individual forecasts, which I recommend to be 10. |
| Final combined forecast | I recommend you cap the rescaled combined forecasts within the range -20 to +20, as for individual forecasts. |

Now you can forecast price movements for a particular instrument you are ready to translate that into actual trades. The first step in doing this is to decide how much money you are willing to put at risk, as you'll see in the next chapter.

---
86. (0.5 × 15) + (0.5 × -10) = 2.5.
87. Naturally this should be done on an out of sample basis, so your weights change during the back-test. After cost performance must be used when generating portfolio weights. I discuss costs more in chapter twelve, 'Speed and Size'.
88. The slow look-back is 4 times the fast, as discussed in appendix B, page 296.
89. You can replicate this result with one of the many online portfolio calculators, such as www.zenwealth.com/businessfinanceonline/RR/PortfolioCalculator.html
90. The diversification multiplier is also a measure of the number of independent bets in the portfolio, as used in the law of active management.
91. A couple of technical points. Firstly strictly speaking diversification multipliers should be calculated on a rolling out of sample basis if based on back-tested data. However as you're not optimising a parameter based on profitability, estimating these single multipliers won't cause serious problems with over-fitting. Secondly when estimating forecast diversification multipliers you can either use the forecasts from each individual instrument, or pool back-tests of different instruments (which is my preferred approach), before calculating correlation matrices.
92. The precise formula and spreadsheet method is in appendix D (page 311).
93. These values assume that you have equal weights in your portfolio and all correlations are identical. So they are an approximation, but very close to the real answer except for extreme portfolios.
94. You shouldn't include the self correlation '1' values when working out the average.
95. The weighted average of the two forecasts is (16.0 × 50%) + (16.0 × 50%) = 16.0. After applying the multiplier the combined forecast is 16.0 × 1.5 = 24.

# Chapter Nine. Volatility targeting

[Image of a matrix: Instruments vs Forecast weights]

D O YOU REMEMBER SERGEI, DISPENSER OF OPAQUE TRADING advice in chapter seven? He told me that there were three issues to consider when deciding how big a position we should have. The first thing to consider was how much we liked the trade. You've dealt with that by creating a single forecast for each instrument you're trading – either a discretionary forecast for semi-automated traders, a constant forecast for asset allocating investors, or a combined forecast for staunch systems traders. Now we're ready to return to Sergei's second question, "How much can you afford to lose?"96

## Chapter overview

| | |
|---|---|
| The importance of risk targeting | Why getting your appetite for risk right is so important and the key issues involved. |
| Setting your volatility target | The measure of how much risk you're prepared to take and how to calculate it. |
| Rolling up profits and losses | How your volatility target should be adjusted when you lose or make money. |
| What percentage of capital per trade | Relating the volatility targeting concept to traditional money management where you limit bets to a specific percentage of capital. |

## The importance of risk targeting
Deciding your overall trading risk is the most important decision you will have to make when designing your trading system. Nearly all amateur traders lose money and most do so because their positions are too large compared to their account size.97 Suffering painful losses is the main reason why both amateurs and professionals meddle with trading systems rather than letting them run unimpeded.

Making this decision correctly involves understanding two things. Firstly you must *understand your system*, in particular its likely performance and whether it's likely to have positive or negative skew. You must avoid overconfidence, as I discussed in chapter one. You should not extrapolate over-fitted back-test results to create high expectations of return. Are you sure your strategy can generate a Sharpe ratio of 2.0 after costs? Are you really, really sure?

Next you must *understand yourself*, in a complete and honest way. Can you face the possibility of regularly losing 5%, 10% or 20% of your own capital in a day?

These points also apply to those paid to manage other people's money. Additionally professionals need to understand their clients' tolerance for losing money. If investors aren't truly comfortable with the risks being taken then you will see them redeeming in droves when large losses occur.

## Setting a volatility target
Imaginary conversation between a financial advisor and myself:
Financial 'expert': "How much risk do you want to take?"
Me: "What do you mean by risk?"
Financial 'expert': "Er... well how would you define your tolerance for losing money?"
Me: "Well it could be how much I'm prepared to lose next year. Or tomorrow. Or next week. Are you talking about the absolute maximum loss I can cope with, or the average, or the worst loss I'd expect 95 days out of 100 (the so called 'Value at Risk')? Which question would you like me to answer?"
Financial 'expert': "Hold on. I need to speak to my supervisor..."

Joking aside, how do we answer this deceptively simple question? To keep things simple I use a single figure to measure appetite for risk – an expected standard deviation, which I call the volatility target. You can measure this as a percentage, or in cash terms, and over different time periods. So for example the daily cash volatility target is the average expected standard deviation of the daily portfolio returns. As it's a cash value you need to specify the currency that your account or fund is denominated in.

When I first discussed risk on page 44 I talked about predictable and unpredictable risks. Your volatility target is the long-term average of expected, predictable, risk. The exact predictable risk you have on any given day will depend on the strength of your forecasts, and on the current expected correlation of asset prices. You'll also face unpredictable risks if your forecast of volatility or correlations is wrong. In any case the actual amount you lose or gain on any given day will be random, since even a perfect estimation of risk only tells you what your *average* gains and losses will be.

I find it's easier to look at an annualised cash volatility target, which will be the annualised expected daily standard deviation of returns. As before you annualise by multiplying by the square root of time; given there are around 256 trading days in a year this will be 16. Beware: the annualised volatility target isn't the maximum, or even the average, you might expect to lose in a year.98 Indeed it's quite probable you will sometimes lose more than that in a year.

It's also easier to separate out your cash account value and the appropriate level of risk to run on that money. The amount of cash you are trading with is your trading capital. You then decide what your volatility target will be as a percentage of that capital. If you multiply this percentage volatility target by your trading capital, then you'll get your volatility target in cash terms. So with a million dollars of trading capital and an annualised 10% percentage volatility target, you would have an annualised cash volatility target of $100,000.

In the rest of the chapter I'll be dealing with the implications of where you set your trading capital and percentage volatility target, rather than setting your cash volatility target directly. This means that amateur traders with £1,000 in their account can use the same guidelines to set percentage volatility target as multi-billion Euro hedge funds.

Here are the points to consider when setting your trading capital and percentage volatility targets:

1. How much can you lose?: How much money do you have to trade or invest?
2. How much risk can you cope with?: Can you afford to lose it all? Can you afford to lose half? What probability of losing half would you be comfortable with? What probability of losing 90% of it over ten years would make you lose sleep?
3. Can you realise that risk?: Given the instruments you are investing in and the safe amount of leverage (if any) you can use, can you actually hit the risk target?
4. Is this level of risk right for your system?: Given the characteristics of your trading system, expected Sharpe ratio and skew, does the amount of risk make sense?

## How much can you lose?
The initial trading capital is the amount of cash you start with, bearing in mind that there is a chance that you might lose all or nearly all of it, although hopefully that's quite unlikely. I'll show you below how to set your percentage volatility target based on exactly how relaxed you are about losses.

For an institutional investor things are usually straightforward; you are given £100 million and you would use 100% of it. Sometimes you might not go 'all in' if you have guaranteed some of the capital, or need to retain cash for potential redemptions.

If you're investing your own money then your trading capital will depend on your savings and how much you are willing to commit to such a risky endeavour. In any case – and I can't emphasise this enough – never put in more than you can afford to lose. Never trade with borrowed money, or money earmarked to pay off debts.99 Even if you follow the advice in this book to the letter there is still a remote chance that you will be unlucky enough to burn through virtually your entire account.

## Can you cope with the risk?
Let's say you decide to put $100,000 of trading capital into your account and run with a 200% volatility target; equating to an annualised cash volatility target of $200,000. Could you cope with losing $20,000 in one day? What about having a cumulative loss, or draw-down, of over $60,000? If it isn't your money, could your client cope with it?

I hope so because you're likely to see those kinds of losses within the first few weeks of trading! As table 20 shows, a $20,000 loss would typically be seen every month, and a $62,000 cumulative loss around 10% of the time.100

TABLE 20: WHAT KIND OF LOSSES DO WE SEE FOR A PARTICULAR VOLATILITY TARGET?

| Expected | Percentage volatility target | | | |
|---|---|---|---|---|
| | 25% | 50% | 100% | 200% |
| Worst daily loss each month | $2,500 | $5,000 | $10,000 | $20,000 |
| Worst weekly loss each year | $6,900 | $14,000 | $28,000 | $55,000 |
| Worst monthly loss every ten years | $16,000 | $32,000 | $63,000 | $80,000 |
| Worst daily loss every 30 years | $5,400 | $11,000 | $22,000 | $43,000 |
| 10% of the time, the cumulative loss will be at least | $9,300 | $15,000 | $30,500 | $62,000 |
| 1% of the time, the cumulative loss will be at least | $11,000 | $18,500 | $37,000 | $75,000 |

The table shows various expected losses (rows), and different percentage volatility targets (columns), given trading capital of $100,000, assuming Sharpe ratio 0.5 and zero skew with Gaussian normal returns.

Now, table 20 assumes you have zero skew in your returns. Are you running a positive skew trend following system, or a negative skew relative value or carry rule? Systems with different skew have varying risk properties. As table 21 shows, the worst days, weeks and months for a negative skew strategy are much nastier than with zero skew. For positive skew strategies large losses are much less likely, as you can see in table 22. However the typical cumulative loss is higher.

With negative skew it's vital to have sufficient capital to cope with the very bad days, weeks and months you will occasionally see. This is especially true with high leverage and the risk your broker will make a margin call at the worst possible time. With positive skew the difficulty is psychological; committing to a system when you spend most of your time suffering cumulative losses.

TABLE 21: HOW DO TYPICAL LOSSES LOOK WITH NEGATIVE SKEW? INDIVIDUAL LOSSES ARE HIGHER THAN IN TABLE 20, BUT CUMULATIVE LOSSES ARE SMALLER

| Expected | Percentage volatility target | |
|---|---|---|
| | 25% | 50% |
| Worst daily loss each month | $3,100 | $6,100 |
| Worst weekly loss each year | $8,500 | $17,000 |
| Worst monthly loss every ten years | $18,100 | $36,000 |
| Worst daily loss every 30 years | $11,500 | $23,000 |
| 10% of the time, the cumulative loss will be at least | $3,700 | $7,400 |
| 1% of the time, the cumulative loss will be at least | $7,100 | $14,000 |

The table shows various expected losses (rows) and different percentage volatility targets (columns), for a negative skew option selling strategy given trading capital of $100,000.101 The strategy has a Sharpe ratio of 0.5 and skew of around -2.

TABLE 22: HOW DO LOSS PATTERNS CHANGE FOR POSITIVE SKEW? WITH POSITIVE SKEW INDIVIDUAL LOSSES ARE MUCH BETTER THAN IN TABLES 20 AND 21, BUT AVERAGE CUMULATIVE LOSSES A LITTLE WORSE

| Expected | Percentage volatility target | |
|---|---|---|
| | 25% | 50% |
| Worst daily loss each month | $2,000 | $4,000 |
| Worst weekly loss each year | $6,100 | $12,000 |
| Worst monthly loss every ten years | $15,000 | $30,000 |
| Worst daily loss every 30 years | $2,800 | $5,700 |
| 10% of the time, the cumulative loss will be at least | $11,000 | $22,000 |
| 1% of the time, the cumulative loss will be at least | $12,000 | $24,000 |

This table shows various expected losses (rows) given different percentage volatility targets (columns), for a positive skew trend following strategy, with trading capital of $100,000.102 The strategy has a Sharpe ratio of 0.5 and skew of around 1.0.

Earlier I said you could frame risk by how much you are prepared to lose in a lifetime. That's difficult to quantify without knowing your life expectancy, so let's assume you will trade for ten years. In table 23 I show the chances of ending a decade-long trading career with less than half, and less than 10%, of your trading capital left, given a certain percentage target volatility.

Only you know how much risk you can cope with. However you, or your clients, must be able to stomach the likely losses involved. If you can't then you should set a lower percentage volatility target, or if possible consider using less initial trading capital.

TABLE 23: WHAT ARE THE CHANCES OF LOSING ALL, OR MOST, OF MY MONEY?

| | Percentage volatility target | | | |
|---|---|---|---|---|
| | 25% | 50% | 100% | 200% |
| Chance of losing half | <1% | 10% | 40% | 93% |
| Chance of losing 90% | <1% | 1.1% | 22% | 88% |

The table shows chances of ending a ten-year trading career losing a given proportion (rows), of initial trading capital given different percentage volatility targets, assuming Sharpe ratio is 0.50 and zero skew.103

## Can you realise that risk?
If you're investing in leveraged derivatives like futures and spread bets then very high levels of risk are attainable, even if they aren't desirable. Such systems can easily run at over 100% annualised target volatility with margin to spare.

But if you can't get enough, or any, leverage then you might have a problem achieving your target volatility. If you are buying short-term government bonds with an expected volatility of perhaps 5% a year, then without leverage it's impossible to create a portfolio with a 50% volatility target. With no leverage you are restricted to the amount of *natural* risk that your instruments have. With only 100% leverage you are limited to twice that natural risk, and so on.

Because it's mostly a problem for non-leveraged asset allocating investors I'll go into more detail about this in the relevant part of part four, chapter fourteen.

## Is there too much leverage?
Even if you are able to leverage up as required to hit a particular percentage volatility target, it would be very unwise if excessive gearing is needed. This is particularly problematic for negative skew instruments and trading strategies, which tend to have low natural risk – until they blow up.

I've mentioned before the huge appreciation of the Swiss franc that happened in just minutes in January 2015. At the start of the day in question the natural risk of holding a position in EUR/CHF was tiny, at around 1% a year. If this was the only instrument you were trading then to achieve a 50% annualised volatility target would have needed 50 times leverage. Retail FX brokers had no compunction in allowing this, with leverage up to 500 times available from some providers.

If you had been on the wrong side of this move, with your entire trading capital leveraged 50 times, then a 2% appreciation would have wiped you out. But the actual move was over 16%! Only those with leverage of 7 times or less would have survived the day, which implies a maximum achievable 7% volatility target.

You should ensure that with a given percentage volatility target any individual position would not wipe you out after the largest conceivable move. Diversifying amongst many different instruments will also help, and we'll return to that in chapter eleven, 'Portfolios'. A 16% move with 50 times leverage would have been just about survivable if EUR/CHF was only 10% of your portfolio, assuming no other losses had occured elsewhere.

Ideally such low volatility instruments, requiring insanely high leverage, should be excluded from any trading system.

## Is this the right level of risk?
Suppose you've decided on a 200% volatility target. You've got the leverage you need; but you haven't got carried away. Furthermore you're confident that you will cope with the spectacularly bumpy ride tables 20 to 23 imply you'll be getting. Assuming you are a profitable trader, should you then set your target at 200% and expect to end up incredibly wealthy through the magic of compound interest?

The short answer is no. There is a Goldilocks level of risk – not too little and not too much. Even if you are willing and able to go above this level you shouldn't, as you will end up with more than your tongue getting burnt.

Naively if you expect to be profitable then you should bet as much as you're allowed to. However this ignores the *compounding* of returns over time. Suppose you have a fantastic expected average return of 100% on each trade for a given bet size. You then lose 90% of your capital on your first trade and make 190% on your next trade. Unfortunately there is only 29% of your cash left, even though you've achieved the expected average return of 100% per trade.104 To maximise your final profits, the optimal bet to make is actually a quarter of the original size.

Nearly all professional gamblers, many professional money managers and some amateurs in both fields know that this optimal point should be calculated using something called the Kelly criterion.105 Kelly has some useful but potentially dangerous implications for how you should set your percentage volatility target.

A simple formula can be used to determine how you should set your volatility target, given the underlying Sharpe ratio (SR) of your trading system. You should set your volatility target at the same level as your expected SR. So if you think your annualised SR will be 0.25 then you should have a 25% annualised volatility target.
