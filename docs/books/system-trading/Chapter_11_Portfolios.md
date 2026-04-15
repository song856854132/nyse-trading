# Chapter Eleven. Portfolios

QUESTION: WHAT DO MANY TRADERS AND AMATEUR investors who buy individual equities rather than invest in collective funds have in common? Answer: They both tend to have too few assets in their portfolios.

Research into individual investors finds many hold less than five shares, whilst traders often only prefer to deal with one or two markets where they feel most expert. So far I haven't helped solve this problem, since in the last chapter I showed you how to put together a trading subsystem which holds positions in just a single instrument.

But diversification really is the only free lunch in investment. Allocating across different asset classes can easily double your expected Sharpe ratio, as we saw in chapter two (page 52). It's best to simultaneously run a *portfolio* of as many trading subsystems and instruments as possible and allocate your trading capital between them. To allocate within this portfolio you will use instrument weights. Even though semi-automatic traders don't have a fixed set of assets they should also try and hold a number of positions in several instruments at once.

## Chapter overview

| | |
|---|---|
| Portfolios and instrument weights | What is a portfolio of trading subsystems and what are instrument weights? |
| Instrument weights – Asset allocators and Staunch systems traders | How to allocate weights when you are trading a fixed set of trading subsystems. |
| Instrument weights – Semi-automatic traders | The special case of semi-automatic traders who have multiple bets on, but not necessarily in the same instruments. |
| Instrument diversification multiplier | Accounting for diversification between subsystems for different instruments. |
| A portfolio of positions and trades | Calculating what position you should hold, given your instrument weights, and what trades you should generate. |

## Portfolios and instrument weights

This section is suitable for all readers

In an earlier chapter I used an example of a three asset portfolio to illustrate the black art of portfolio optimisation. The three assets were the S&P 500, NASDAQ and a 20 year US Bond. Suppose now that you're asset allocator investors who are trying to allocate capital between these instruments, or staunch systems traders who have forecasting rules that predict their returns. Alternatively, imagine that you're a semi-automatic trader who happens to have placed bets on each of these three assets.

Using the methods in the previous chapter you would calculate three subsystem positions, one for each instrument. Each position will depend on your forecast and how risky each instrument is. You would also have pretended to put all of your trading capital into trading each one of these systems. Effectively you will create three trading subsystems, each of which nominally uses your entire capital to trade one instrument.

In practice though you're going to share your capital across a *portfolio* of subsystems; similar to the way I created a portfolio with the same three underlying assets in chapter four. Each instrument's trading subsystem will get a positive instrument weight, with weights summing to 100%. Your portfolio weighted position will be the instrument's subsystem position, multiplied by the relevant instrument weight to reflect its portfolio share. Once you have this you can work out what trades are needed for each instrument.

As I'll show you later in the chapter you also need to account for the effect of portfolio diversification. But first we need to consider how to calculate the instrument weights.

## Instrument weights – asset allocators and systems traders

Asset Allocating Investor
Staunch Systems Trader

Asset allocating investors run a fixed portfolio of trading subsystems, one per instrument, each consisting of a single trading rule – the 'no-rule' rule producing a constant identical forecast. Staunch systems traders have a group of trading rules whose forecasts are combined and then scaled into a position. In both cases you are allocating your trading capital between subsystems relating to a fixed set of instruments. This is different to traditional portfolio allocation, where you allocate capital directly to positions in each instrument.

Because of your hard work in the last couple of chapters all the subsystems will be volatility standardised and have the same expected standard deviation of returns. As you saw in chapter four, this makes the job of portfolio optimisation simpler. You can easily use the handcrafting method introduced in chapter four to determine the instrument weight each subsystem gets. It's also possible to use bootstrapping as an alternative.115

To handcraft your weights you need to group the assets and for this you need correlations. There are two alternatives that can be used to find these. Firstly you can estimate them using back-tested data. Alternatively if you don't have back-tested correlations then tables 50 to 55 (from page 305 in appendix C) give indicative correlations between instrument returns.

But you need the correlations between trading subsystem returns, *not* the returns of the underlying instruments. For dynamic trading systems the correlations between subsystem returns tend to be lower than those of the underlying instruments. A good approximation is that the correlation between subsystem returns will be 0.70 of the correlation of instrument returns. So if two assets have a correlation of 0.5 between their instrument returns in appendix C, then their subsystems will have a correlation of 0.7 × 0.5 = 0.35.

Because asset allocating investors use a static strategy, the correlation of your subsystems is likely to be much closer to what you'd have with fixed long positions in the underlying instruments. So rather than multiplying the correlations in appendix C by 0.7, I recommend that you use them without adjustment.

In chapter four I showed you how to change portfolio weights if you had evidence that assets had different Sharpe ratios. But I wouldn't recommend adjusting instrument weights for Sharpe ratios, since there's rarely enough evidence of different performance between subsystems for different instruments, even once we account for different levels of costs. I come back to this in the chapter on 'Speed and Size'.

Let's look at an example. Here's how I would handcraft the instrument weights for the simple example of three instruments (S&P 500, NASDAQ, 20 year bond). Row numbers refer to the relevant rows of table 8 (page 89).

| | |
|---|---|
| First level grouping<br>Within asset classes | Group one (bonds): One asset, so 100% in 20 year bond. Row 1.<br>Group two (equities): Two assets, 50% in each. Row 2. |
| Second level grouping<br>Across asset classes | I have two groups to allocate to, each gets 50%. Row 2. |

This gives me the same weights I had in chapter four for the actual assets, as shown in table 28. Of course this wouldn't normally be the case; it's only because this is a trivial example with no more than two assets in each group, and the same groupings as before.

TABLE 28: IN THIS SIMPLE EXAMPLE HANDCRAFTED WEIGHTS FOR TRADING SUBSYSTEMS ARE THE SAME AS FOR THE ASSETS THEMSELVES

| | Handcrafted weight |
|---|---|
| US 20 year bond | 50% |
| S&P 500 equities | 25% |
| NASDAQ equities | 25% |

I give more complex examples of handcrafting instrument weights in each of the example chapters in part four.

## Instrument weights – semi-automatic trading

Semi-automatic Trader

Semi-automatic traders don't have fixed portfolios of instruments, always creating forecasts and holding positions in each and every instrument. Instead you're likely to have a relatively small number of opportunistic positions (bets) on your books at any one time, drawn from a larger pool of potential trading ideas. Each time you enter a new bet for a different instrument you need to make a forecast, and then size your positions according to the size of your account and the risk of the instrument.

This presents a problem because the make-up of your portfolio, and hence the correlation of returns, will change over time as different instruments come in and out. The simplest thing to do is to allocate trading capital *equally* between potential opportunities. To ensure your risk is properly controlled you must also limit the *maximum* number of bets that can be placed at any time.

So you should allocate your risk equally between a notional maximum number of concurrent bets, each of which represents a potential trading subsystem. For example if the notional maximum number is ten bets this implies each instrument weight will be 100% divided by 10, which equals 10% for each instrument.

For reasons that will become clear later in this chapter, I recommend that this maximum shouldn't be more than 2.5 times the *average* number of bets you expect to be holding over time.

## Instrument diversification multiplier

Once you've parcelled out your trading capital to each trading subsystem you're faced with a problem you might have seen before in chapter seven, which is the issue of diversification reducing your risk. If you skipped that chapter please go back and read the concept box on page 138. Diversified portfolios of volatility standardised assets like trading subsystems nearly always have a lower expected standard deviation of returns than the individual assets they are trading. The lower the average correlation, the worse the undershooting of risk will be.

You already know that the correlation between the two equity indices and the bond in the simple example is very low (the rule of thumb value from table 50 in appendix C is 0.1, and the estimated value I calculated in chapter four was negative). The correlation between the subsystem returns is likely to be even lower. So it's very unlikely that you'll get the same desired level of average risk from a portfolio of these three instrument subsystems as you would if you ran each one individually.

As in chapter seven you're going to need to apply a factor to account for the diversification in your portfolio: an instrument diversification multiplier. You multiply the portfolio weighted positions you've calculated by this multiplier to ensure that the overall portfolio has the right level of expected risk.

Staunch Systems Trader
Asset Allocating Investor

Asset allocating investors and staunch systems traders should use the correlations between the returns of each instrument trading subsystem to calculate the expected degree of diversification in the portfolio.

You have the option of either using estimated correlations from a back-test, or using rule of thumb correlations.116 Once again be warned that tables 50 to 55 (from page 305 in appendix C) give indicative correlations between instrument returns. Staunch systems traders can multiply these by 0.7 to give the correlation between trading subsystem returns. Asset allocating investors should use instrument return correlations without adjustment.

Once you have the correlations, from whichever source, you have two options for the calculation: either use the formula in appendix D on page 311, or the approximations in table 18 (page 140). The number of assets in table 18 will be the number of subsystems you are running.

Let's return to the simple three asset example. From table 50 the correlation between bonds and equities is 0.1, and from table 54 the correlation between the S&P 500 and NASDAQ is around 0.75.117 I'll assume for the sake of the example that I have a dynamic trading system, so I'm not a static asset allocator. This implies I should multiply correlations by 0.7, giving the correlation matrix in table 29. The average correlation is around 0.25, and from table 18 with three assets I get a diversification multiplier of 1.41.118

It's possible to get very high values for the diversification multiplier, if you have enough assets, and they are relatively uncorrelated. However in a crisis such as the 2008 crash, correlations tend to jump higher exposing us to serious losses – an example of unpredictable risk. To avoid the serious dangers this poses I strongly recommend limiting the value of the multiplier to an absolute maximum of 2.5.

TABLE 29: CORRELATION MATRIX OF TRADING SUBSYSTEMS FOR THREE EXAMPLE ASSETS

| | Bond | S&P | NASDAQ |
|---|---|---|---|
| US 20 year bond | 1 | | |
| S&P 500 | 0.07 | 1 | |
| NASDAQ | 0.07 | 0.53 | 1 |

*Correlations are 0.7 of the indicative correlations of instrument returns from tables 50 and 54 in appendix C.*

Semi-automatic Trader

For semi-automatic traders I recommend using the following simple calculation. The instrument diversification multiplier should be your *maximum* numbers of bets divided by the *average* number of bets.119 So if you had an average of four bets on at any given time, with a maximum of five, then your multiplier would be 5 ÷ 4 = 1.25.

I advocate that the multiplier is limited to a maximum of 2.5, since if you end up frequently trading more than your average then your expected risk will be too high. As I said earlier this means it's advisable that the maximum number of bets isn't more than 2.5 times the expected average.

## A portfolio of positions and trades

This section is relevant to all readers

You're now in a position to see how a complete trading system for the simple three asset example could work.

I'm assuming that I use futures to trade these assets and that I have an annualised cash volatility target of €100,000. The price volatility and exchange rates are correct as I write, but I've used some arbitrary forecasts to make this example interesting but not too specific. You'll see some more specific examples in part four.

First of all tables 30 and 31 are there to remind you of the calculations in earlier chapters for each of the three trading subsystems.

TABLE 30: CALCULATING THE INSTRUMENT VALUE VOLATILITY FOR THE THREE ASSETS IN THE EXAMPLE PORTFOLIO

| | (A)<br>Price volatility % per day | (B)<br>Block value | (C)<br>Instrument currency volatility A × B | (D)<br>Exchange rate USD/EUR | (E)<br>Instrument value volatility C × D |
|---|---|---|---|---|---|
| US 20 year bond | 0.52 | $1500 | $780 | 0.88 | €686 |
| S&P 500 equities | 0.84 | $1145 | $956 | 0.88 | €841 |
| NASDAQ equities | 0.87 | $880 | $766 | 0.88 | €674 |

*Values in table assume we're using futures and assuming a Euro investor. Figures correct as of January 2015.*

TABLE 31: CALCULATING THE SUBSYSTEM POSITION FOR THE THREE TRADING SUBSYSTEMS IN THE EXAMPLE PORTFOLIO

| | (F)<br>Instrument value volatility | (G)<br>Daily cash volatility target | (H)<br>Volatility scalar G ÷ F | (J)<br>Combined forecast | (K)<br>Subsystem position (H × J) ÷ 10 |
|---|---|---|---|---|---|
| US 20 year bond | €686 | €6,250 | 9.11 | 10 | 9.11 |
| S&P 500 equities | €841 | €6,250 | 7.43 | -10 | -7.43 |
| NASDAQ equities | €674 | €6,250 | 9.28 | -15 | -13.9 |

*The investor has a €100,000 cash volatility target, which implies a €6,250 daily target.120 Forecasts are arbitrary.*

The subsystem positions in column K assume one instrument is traded with the entire trading capital. In table 32 I bring in the instrument weights and instrument diversification multiplier that I calculated earlier in this chapter. So to get the final portfolio instrument position I just need to multiply each subsystem position by the relevant instrument weight and the multiplier which compensates for the diversification in the portfolio.

TABLE 32: CALCULATING THE PORTFOLIO INSTRUMENT POSITION FOR THE EXAMPLE PORTFOLIO

| | (K)<br>Subsystem position | (L)<br>Instrument weight | (M)<br>Instrument diversification multiplier | (N)<br>Portfolio instrument position K × L × M |
|---|---|---|---|---|
| US 20 year bond | 9.11 | 50% | 1.41 | 6.42 |
| S&P 500 equities | -7.43 | 25% | 1.41 | -2.62 |
| NASDAQ equities | -13.9 | 25% | 1.41 | -4.91 |

*The table is using the instrument weights and diversification multiplier derived earlier in the chapter.*

The final table 33 shows how I generate actual trades. To begin with I round the instrument position to get a rounded target position. This is the first time that I've rounded in my calculations. I then compare this to the current position which I already have. If I'd only just started trading this will be zero, but column P shows some arbitrary current positions to demonstrate the logic.

Finally I can calculate the size of any trade needed. I recommend that if the current position is within 10% of the rounded target position, then you shouldn't trade. I call this position inertia.

So for example if I had a target position of 50 crude oil contracts and my current position was between 45 and 55 contracts then I wouldn't bother trading. Conversely if the current position was 42 contracts versus a target of 50, I'd buy 8 contracts to hit my target. In the table the positions are relatively small so position inertia isn't used.

TABLE 33: CALCULATING THE REQUIRED TRADE GIVEN THE ROUNDED TARGET POSITIONS AND SOME ARBITRARY CURRENT POSITIONS

| | (N)<br>Portfolio instrument position | (P)<br>Rounded target position Round (N) | (Q)<br>Current position | (R)<br>Trade P - Q |
|---|---|---|---|---|
| US 20 year bond | 6.42 | 6 | 4 | Buy 2 |
| S&P 500 equities | -2.62 | -3 | -2 | Sell 1 |
| NASDAQ equities | -4.91 | -5 | -5 | None |

CONCEPT: POSITION INERTIA

Position inertia is a way of avoiding small frequent trades that increase costs without earning additional returns.

For example suppose your desired unrounded position is 133.48 Italian government bond futures, which is 133 contracts rounded. If your desired position goes to 133.52, 134 rounded, you'd buy one contract. If it drops back to 133.48 you would sell again. But the changes in desired position were only 0.04. Is it worth buying and selling, paying two lots of commission and market spreads, for such a small adjustment? Probably not.

The solution is to avoid trading until the target position is more than 10% away from the current position. For Italian bond futures the first movement in the desired position to 133.52 wouldn't result in a trade, since your current position of 133 would only be 0.75% away from the desired rounded position of 134. In fact the target position would have to go to 147 blocks before you traded.

Position inertia significantly reduces trading costs, which as you'll see in the next chapter can seriously affect your returns. My research shows position inertia usually has a negligible effect on pre-cost performance, so there is no downside to using it.121

Trades can be done manually or by an algorithm if you have a completely automated system. There is information on how I automate my own trading with simple algorithms on my website (see appendix A).

## Summary for creating a portfolio of trading subsystems

| | |
|---|---|
| Subsystem position | This is the number of instrument blocks you hold in each trading subsystem, given your forecasts, the instrument riskiness and your daily cash volatility target, as calculated in chapter ten. It is in instrument blocks. |
| Instrument weights | Each trading subsystem should have an instrument weight. Weights should add up 100%.<br>Staunch systems traders and asset allocating investors can use handcrafting or bootstrapping to find weights. Correlations can be estimated from a back-test of trading subsystems, or using rules of thumb. In the latter case you should multiply instrument return correlations from appendix C by 0.7 if you're trading a dynamic strategy, or by 1.0 if you're asset allocating investors using fixed constant forecasts.<br>Semi-automatic traders should use equal instrument weights of 100% divided by the maximum number of possible bets. |
| Instrument diversification multiplier | For asset allocating investors and staunch systems traders this is calculated using the correlation of trading subsystem returns. The multiplier can be calculated precisely using the formula in appendix C on page 311 or approximately using table 18 on page 140.<br>For semi-automatic traders this will be equal to the maximum number of bets divided by the average number of bets.<br>I recommend that in all cases the multiplier is limited to a maximum value of 2.5. |
| Portfolio instrument position | Equal to instrument subsystem position multiplied by instrument weight and then by instrument diversification multiplier. |
| Rounded target position | This is the portfolio instrument position rounded to the nearest integer number of instrument blocks. |
| Desired trade | After calculating the rounded target position you compare this to your actual current position and generate the necessary trade. If the current position is within 10% of the target then you don't need to trade (position inertia). |

This completes the main part of the framework. I've now shown you how to create a complete trading system, consisting of a portfolio of trading subsystems. In the next chapter we will consider how to design systems which cope with the varying costs you'd see trading at different speeds, and with larger or smaller amounts of capital.

115. To use bootstrapping you need to be able to back-test the performance of each of the trading subsystems separately. Ideally this should be done on a rolling out of sample basis. As I'll discuss in chapter twelve, 'Speed and Size', any returns that are calculated should be after costs.
116. Any negative correlations you estimate should be floored at zero to avoid an excessively large multiplier.
117. Actually table 54 in appendix C tells us the correlation between equities of different industries. Given the technology heavy nature of the NASDAQ compared to the S&P 500 this seems a good enough approximation, and is very close to the real number which we estimated in chapter four.
118. You should remove the self correlation values of 1.0 before calculating the average.
119. This essentially assumes that all of a semi-automatic trader's bets are always perfectly correlated, which is very conservative. Here is the proof of this result. Suppose you're aiming for a daily volatility target of $1,000 and have an average of five bets, with a maximum of 10. All portfolio weights are 100% ÷ 10 = 10%. Each trading subsystem will also have a volatility target of $1,000. Once multiplied by the portfolio weight each subsystem position will have an average volatility of $100. On average with five bets, all of which are perfectly correlated, your daily portfolio returns will be 5 × $100 = $500 (note had they all been uncorrelated the risk would only be $223). So to hit the overall target of $1,000 you need a diversification multiplier of 2.
120. To go from annualised to daily we divide by the 'square root of time', assuming a 256 day business day year that means you should divide by 16.
121. This seems to be true for trading rules with holding periods of greater than a few days. If you're trading faster you probably shouldn't use position inertia (or use a lower value than 10%), but as we'll see in chapter twelve it's very hard to trade that quickly and make money.