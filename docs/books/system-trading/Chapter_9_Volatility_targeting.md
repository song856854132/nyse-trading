You can see this in figure 21, where for an SR 0.5 system the best performance is achieved with the optimal 50% volatility target. This is true for all three systems shown, regardless of skew.

FIGURE 21: KELLY CRITERION IMPLIES THE OPTIMAL RISK PERCENTAGE FOR A SHARPE RATIO 0.5 SYSTEM IS 50%. WITH HIGHER RISK THINGS GO BADLY, ESPECIALLY FOR NEGATIVE SKEW STRATEGIES.
The X-axis shows the percentage volatility target and the Y-axis the geometric mean of returns which Kelly optimises.

TABLE 24: BIG SHARPE MEANS BIGGER RISK AND EXPONENTIALLY BIGGER PROFITS
| Expected Sharpe ratio | Optimum percentage volatility target | Expected return |
|---|---|---|
| 0.2 | 20% | 4% |
| 0.5 | 50% | 25% |
| 0.75 | 75% | 56% |
| 1.0 | 100% | 100% |
| 2.0 | 200% | 400% |

The table shows the expected annual return (as a percentage of trading capital), given different Sharpe ratio (SR) (rows) and using the optimal Kelly percentage volatility target. Expected return is SR multiplied by percentage volatility target.

This finding is potentially dangerous when used by an over confident investor. It’s very easy with back-testing software to get over-fitted performance with a Sharpe ratio (SR) of 2, 3 or even higher. If you believe those are attainable then a risk percentage of 100% or 200% seems justified. As table 24 shows, running at a 200% risk with SR of 2.0 implies huge returns of 400% a year!
Unfortunately many people with capital of $20,000 will conclude it’s possible to earn 400% a year, or $80,000, as full-time traders. There are also plenty of brokers who will happily provide them with the necessary leverage. Most of these people will quickly lose their $20,000, as they won’t achieve their expected SR. It’s very difficult to know exactly what your true Sharpe ratio really would have been in the past, with back-tests giving you only a rough upwardly estimate, and it’s utterly impossible to know what SR to expect in the future.
Even if you had a crystal ball, and knew your expected Sharpe precisely, you could be unlucky and have a decade or more of sub-par performance. Figure 21 shows that if you realise an SR of only 0.5 then a 200% volatility target will see you ending up deep underwater. In general if you get your estimate of SR wrong and bet more than the optimal then you have a high chance of losing your shirt.

Recommended percentage volatility targets
I run a highly diversified futures trading system with around 45 instruments, eight trading rules drawn from four different styles, and 30 trading rule variations. In a 35 year back-test, conservatively fitted with out of sample bootstrapping, it has a Sharpe ratio (SR) of around 1.0 after costs, but the highest volatility target I’d advocate using for it is 37%, rather than the 100% suggested by the Kelly criterion and the back-tested SR.^106 Why such a conservative number – am I a wimp?
There are several reasons for my caution. Firstly, it’s unlikely a back-tested SR will be achieved in the future. On average realised performance is never as good as in back-tests. This is because it’s very easy to over-fit if you ignore the advice in chapters three and four. Additionally it’s difficult with ideas first testing to avoid using only trading rules that you already know would have worked.
Even if you could avoid over-fitting actual profits are unlikely to be as high as they could have been in the past. This is because future asset returns are likely to be lower than in the historical data set we usually use for back-testing, as I discussed in chapter two, ‘Systematic Trading Rules’, in the section on achievable Sharpe ratios (from page 52).
To find realistic achievable SR from back-test results a good rule of thumb is to use the ratios in table 14 (page 100). These suggest that for an out of sample bootstrap, as I’ve used in my own system, a ratio of 0.75 should be applied to find a more realistic Sharpe ratio. Much lower ratios should be used if you haven’t been as careful with your fitting. I also said in chapter two that I think the absolute maximum SR that staunch systems traders should expect to achieve is 1.0, regardless of how good their back-test is.
Secondly, using the full Kelly criteria is far too aggressive, because of the risk of getting a poor run of luck and the large drawdowns that can result, even if SR expectations are correct.^107 In table 23 someone using the correct Kelly target of 50% would have a 10% chance of losing half their money after ten years; which most people would find worrying. It’s far better to use Half-Kelly and set your risk at half the optimal. Column A of table 25 shows the recommended percentage volatility target for a given realistic back-tested SR.
For my own system I started with the back-tested Sharpe ratio of 1.0. Multiplying by 0.75 (as I’m using out of sample bootstrapping) from table 14, this gives me a realistic SR of 0.75. With full Kelly criterion betting that would be a 75% volatility target, which I then halved to get 37% (rounding down).
This assumes your trading system, like mine, has zero or positive skew. You should be very careful if you have expected negative skew. As figure 21 shows, the penalty for too much risk is greater with negative skew than when skew is positive, or zero. As I discussed in chapter two, many negative skew strategies have fantastic SR in back-test, but I advise you to run them at half the risk you’d use for a more benign trading system. Column B of table 25 shows the recommended percentage volatility target for negative skew systems.

TABLE 25: WHAT VOLATILITY TARGET SHOULD STAUNCH SYSTEMS TRADERS USE?
| | Recommended percentage volatility target | |
|---|---|---|
| Realistic back-tested SR | (A) Skew>0 | (B) Negative skew |
| 0.25 | 12% | 6% |
| 0.40 | 20% | 10% |
| 0.50 | 25% | 12% |
| 0.75 | 37% | 19% |
| 1.0 or more | 50% | 25% |

The table shows the recommended percentage volatility target for those who can back-test their dynamic trading systems, depending on the skew of returns (columns) and achievable back-tested Sharpe ratios (SR) (rows) after making adjustments to simulated results from table 14 on page 100. Optimal volatility target is calculated using Half-Kelly. For negative skew strategies this is cut in half again. We assume a maximum SR of 1.0 is achievable.

The returns of asset allocating investors are limited by their use of a static trading strategy. With a small, relatively undiversified portfolio you shouldn’t expect high Sharpe ratios. As I said in chapter two, if you’re holding a dozen equities in different industries but from the same country then you probably will achieve an SR of around 0.20. Those with larger portfolios diversified across multiple asset classes could get a maximum realistic SR of 0.4.
Column C of table 26 shows the correct targets given asset allocators’ SR expectations. However, as you’ll see in chapter fourteen, it’s unlikely even this level of volatility can be achieved as these investors don’t use leverage.

Semi-automatic traders have systems which cannot be back-tested and usually have a small, relatively un-diversified, set of ad-hoc instruments. I would initially assume an achievable SR of 0.20 unless you are very experienced, are trading across multiple asset classes, and have a good track record with real money. As you saw in chapter two, in my opinion an SR of 0.5 is the maximum safe achievable level, so you should set the volatility target at no more than 25%.
Again the target should be halved if you are trading a strategy that is likely to have negative skew, such as selling option volatility, or exhibits a similar return pattern with steady profits on most bets with occasional large losses. Columns D and E of table 26 show the appropriate volatility targets for this type of trader.

TABLE 26: WHAT VOLATILITY TARGET SHOULD ASSET ALLOCATING INVESTORS AND SEMI-AUTOMATIC TRADERS USE?
| Expected SR | Recommended percentage volatility target | | |
|---|---|---|---|
| | (C) Asset allocating investor | (D) Semi-automatic trader, zero or positive skew | (E) Semi-automatic trader, negative skew |
| 0.20 | 10% | 10% | 5% |
| 0.30 | 15% | 15% | 7% |
| 0.40 | 20% | 20% | 10% |
| 0.5 or more | 20% | 25% | 12% |

This table shows the recommended percentage volatility target depending on the type of trader and expected skew (columns), and Sharpe ratio (SR) expectations (rows). The optimal volatility target is calculated using Half-Kelly. We assume asset allocators shouldn’t expect more than 0.40 SR and semi-automatic traders won’t get more than 0.50 SR. Asset allocators are assumed to have zero skew. We halve volatility targets for negative skew semi-automatic trading.

This implies that nobody will use more than a maximum 50% volatility target and most people should use less. Tables 20 to 23 illustrate that a 50% annualised volatility will mean some pretty substantial losses from time to time. Just because the volatility targets in tables 25 and 26 are optimal it doesn’t mean they will suit you, or that your broker will permit them. It just means you should never run a higher risk target than this.

When the percentage volatility target should be changed
I don’t advocate changing your percentage volatility target since there is a potential risk of meddling; reducing it when you don’t trust your system and increasing it when it agrees with you. The exception is if you have grossly miscalculated your tolerance for risk. You begin trading on day one with a 50% target, but the first big loss then sends you or your investors into a panic. In this case you should significantly reduce your percentage target. However it should ideally be a one off change and only ever downwards.
To avoid this scenario it’s better to start with significantly lower trading capital and gradually increase it until you have the full amount invested. Keep the percentage volatility target fixed and allow your cash volatility to increase up to the point just before you get uncomfortable. This also helps with gaining confidence in your trading strategy and testing any automated systems.

Rolling up profits and losses
Once set your percentage volatility target shouldn’t need changing. However your trading capital will definitely change from its initial value. This implies that your cash volatility target will also be adjusted over time.
Let’s imagine you have trading capital of $100,000 and after reading this chapter you’ve decided on a 30% volatility target. You begin trading with the appropriate $30,000 annualised cash volatility target. Then on day one you lose $2,000. Should you continue to use a $30,000 volatility target?
You should not. The implication of the Kelly criterion is that you should adjust your risk according to your current capital. You did have $100,000 of capital, but now you only have $98,000. Instead of having a 30% volatility target ($30,000 of $100,000) you effectively have a target of $30,000 divided by $98,000 = 30.6%. This might not seem a big deal, but you are now betting more than you intended and you’ve slightly increased your chances of going bankrupt. If you make further losses the situation could deteriorate fast.
The correct thing to do is to reduce your volatility target to 30% of your current capital of $98,000, or $29,400.
Now suppose things start to improve and you make $2,000 back. Your accumulated losses have reduced to zero and your volatility target will be back to 30% of $100,000, or $30,000. After another profitable day making $3,000 you’re now in positive territory with an account value of $103,000 – higher than your starting capital. Should you now increase your risk appetite above its initial level?
If you want to maximise your wealth then Kelly says you should roll up your profits and increase your capital.^108 The new volatility target will be 30% of $103,000, or $30,900. This means you will be compounding your returns, which over the long run will increase them faster.
You should also reduce your trading capital, and hence your cash volatility target, if you withdraw money from your trading account or investors redeem. Similarly if you put more funds in then you would normally increase your maximum capital. There are exceptions such as if you are putting cash into a leveraged account to meet margin or reduce borrowing, but you don’t want to increase the amount of capital at risk.
In my own trading an automated process checks my account value, and adjusts risk accordingly, on an hourly basis. If your system is not automated and if you are running with more than a 15% volatility target I would recommend checking at least daily. With a lower target you can check more infrequently, but if you’re using leverage I’d advise always calculating your volatility target at least once a week.

What percentage of capital per trade?
Traditional money management systems allocate a certain percentage of trading capital to be risked on each trade or bet. If you’re familiar with these systems you might be wondering how this relates to the volatility targeting done here. It is possible to infer the percentage volatility target that is implied for a particular trading system if you know the approximate holding period, the average number of positions held and the maximum amount of capital put at risk on each trade. You just need to assume that the average bet is half the maximum, which is the same ratio between my recommended average forecast of 10 and maximum of 20.
Table 27 gives the results, assuming an average of two positions are held at once. If a greater or fewer number are traded on average, then you just need to multiply or divide the figures appropriately. So with an average of four positions you’d double them, and for a single position halve them.

TABLE 27: WHAT IS THE VOLATILITY IMPLIED BY A TRADING SYSTEM’S HOLDING PERIOD AND BET SIZE?
| | Implied percentage volatility target | | | | |
|---|---|---|---|---|---|
| | Maximum percentage of capital at risk per trade | | | | |
| Average holding period | 1% | 2.5% | 5% | 10% | 20% |
| 1 day | 40% | 100% | 200% | ! | ! |
| 1 week | 16% | 40% | 80% | 160% | ! |
| 2 weeks | 8% | 19% | 38% | 76% | 152% |
| 6 weeks | 4% | 10% | 21% | 41% | 82% |
| 3 months | 3% | 7% | 13% | 27% | 53% |

The table shows the implied annualised percentage volatility target for a given average holding period (rows) and maximum percentage of capital allocated to each bet (columns), assuming an average of two bets are held in the portfolio.

“!” indicates volatility greater than 200% per year.

As an example take the system which I briefly discussed in the introductory chapter. This held positions for around a week, with no more than 10% of capital at risk. Let’s assume on average that two bets are made at once, although the author wasn’t clear on this point (a common shortcoming in trading books).
This all sounds fairly sedate but from the table this works out to a suicidal 160% volatility target. If this target is Kelly optimal then the achievable Sharpe ratio must be at least 1.6, implying an expected return of 1.6 × 160% or 256% a year! There is some serious overconfidence at work here. Worse still, this is nowhere near the most aggressive system I’ve ever seen.

Summary of volatility targeting

| Percentage volatility target | Desired long run expectation of annualised standard deviation of percentage portfolio returns. A maximum of:<br>• The level of risk that you are comfortable with given tables 20 to 23.<br>• What is practically attainable given your access to leverage and the natural risk of your instruments (see the asset allocating investor example in part four for more details).<br>• The highest level that is safe given the natural volatility of your instruments, and how much leverage they need. Avoid very low volatility instruments requiring insanely high leverage.<br>• The recommended percentage volatility in tables 25 and 26, depending on the back-tested or expected Sharpe ratio and skew of your trading system, and the type of trader or investor you are.<br>Percentage volatility target should remain unchanged. |
|---|---|
| Trading capital | The amount of capital you currently have at risk in your account.<br>Every day you should add profits and any injections of funds. Deduct any losses and withdrawals made from the account.<br>Measured in currency. |
| Annualised cash volatility target | Long run expectation of annualised standard deviation of daily portfolio returns. Equal to the trading capital multiplied by the percentage volatility target.<br>Measured in currency. |
| Daily cash volatility target | Long run expectation of daily standard deviation of daily portfolio returns. Annualised cash volatility target divided by ‘the square root of time’, which for a 256 business day year is 16.<br>Measured in currency. |

In the next chapter I will come back to the final piece of advice I got from Sergei and think about how the risk of an instrument determines what size position we should take.

Chapter Ten. Position Sizing

LET’S COME BACK TO SERGEI’S THREE QUESTIONS FROM chapter seven. First, how much do you like this trade? This is the forecast for each instrument. Secondly, how much can you afford to lose? You should know how many chips of trading capital you’re willing to put down on the hypothetical casino baize depending on your desired target volatility.
So far, so good. But how many shares, bonds, spread bet points or futures contracts should you actually buy or sell? What does a combined forecast of -6 and a £1,000,000 annualised cash target volatility mean in practice if you’re trading crude oil futures in New York? To answer this we need to come back to Sergei’s third question: how risky is your trade?
Once you know this you can move from the abstract world of forecasts and trading rules to deciding the size of actual positions in real financial instruments.

Chapter overview

| How risky is it? | If you own one unit of an instrument how much risk does that expose you to? |
|---|---|
| Volatility target and position risk | What is the relationship between your cash volatility target and the risk of each instrument? |
| From forecast to position | Given how confident you are in your forecasts, the cash volatility target you have and the position risk, what size position should you be holding? |

How risky is it?
What is the expected risk of holding an instrument?^109 If you own one Apple share or one crude oil futures contract, how much danger are you exposed to?
Position block and block value
Let’s start by asking a philosophical question. What exactly is ‘one’ of an instrument? I define this as the instrument block. If ‘one’ of an instrument goes up in price by 1% how much do you gain or lose? This is the block value.
These definitions will seem trivial to equity investors. ‘One’ Apple share is exactly that – one Apple share. If a share has a price of $400 it will cost exactly $400 to buy one block. If the price goes up by 1% from $400 to $404 then you will gain $4. Apple shares, and most other equities, have a natural instrument block of one share and a block value of 1% of the price. Sometimes though to reduce costs you’ll trade in larger blocks, usually of 100 shares. In this case the block value will be 100 × 1% × share price, which is equal to the cost of one share.
But life isn’t always that simple. For example you can use a UK financial spread betting firm to bet on the FTSE falling at £10 a point. If the FTSE rises 1% from 6500 to 6565 you would lose £650. Here the block value is ten times 1% of the price.
Futures contracts also have non-trivial block values. WTI crude oil futures on NYMEX are quoted in dollars per barrel. But each futures contract is for 1000 barrels. This means a 1% move up in