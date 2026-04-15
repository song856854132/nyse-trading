Chapter Twelve. Speed and Size

Speed of trading | The thorny question of how quickly you should trade given the costs of doing so.
Decomposing and calculating the cost of trading | How to work out what you expect to pay in costs, given which instruments you are trading and the characteristics of your trading system.
Using trading costs to make design decisions | Once you know your costs, how you should adjust your system to cope.
Trading with more or less capital | The issues of trading with relatively small or large amounts of capital.
Determining overall portfolio size | Having a smaller account of capital limits how many instruments you can trade. I'll explain how best to determine the size and shape of your portfolio.

Instruments
Trading rule A, variation 1 | A1 forecast for instrument X | Forecast weights | Combined forecast X | Volatility targeting | Position sizing | Subsystem position in X | Instrument weights | Portfolio weighted position in X
Trading rule A, variation 2 | A2 forecast for instrument X
Trading rule B, variation 1 | B1 forecast for instrument X
Trading rule A, variation 1 | A1 forecast for instrument Y | Forecast weights | Combined forecast Y | Volatility targeting | Position sizing | Subsystem position in Y | Instrument weights | Portfolio weighted position in Y
Trading rule A, variation 2 | A2 forecast for instrument Y
Trading rule B, variation 1 | B1 forecast for instrument Y
Customising for speed and size

SO FAR EVERYTHING YOU'VE SEEN IN THE FRAMEWORK IS equally relevant to a nimble amateur trader, holding 100 share positions for a few hours, and the portfolio manager of a massive hedge fund, following trends lasting for months. However in practice these two people will need to trade quite differently to account for the frequency and size of their trades.

In this chapter I will look at how you should design your trading systems given these two interrelated issues of speed and account size.

Chapter overview
Speed of trading
How fast should you trade? If you go long USD/EUR FX at 11:05am on Tuesday 23 September 2014, should you expect to be selling at 11:06? Or by Thursday? Perhaps you will be holding on until December, or even March the following year?

The answer to this question depends on two things: how you expect prices to behave and the cost of each trade. Suppose you have a crystal ball and know with certainty that prices will increase by 10 cents in the next week. If it costs you 1 cent to trade then you should buy as you'll definitely make 8 cents by next Tuesday.122

Unfortunately crystal balls are in short supply. Instead we have forecasts which don't provide certainty, but hopefully shift the odds in our favour. You might have a trading rule where after looking at the back-test you expect to get a Sharpe ratio (SR) of 1.5 before costs. But this strategy pays out two-thirds of its profits in trading costs, so the after-cost SR is just 0.5. If you were running at a 20% volatility target you'd be expecting pre-cost returns of 30% a year, annual costs of 20% and net returns of just 10%.123 Is it wise to trade this rule?

Personally I think it is very unwise indeed. If the actual pre-cost SR turned out to be less than 1.0, giving raw returns below 20% a year, then the strategy will lose money after costs. You'd be trading far too quickly relative to the available pre-cost performance.

Overtrading is a result of overconfidence, one of the cognitive biases I discussed in chapter one. Only someone who was very bullish would assume the realised pre-cost SR would definitely be 1.0 or over in actual trading. You shouldn't trade systems like this and hope for the best. Instead it's much better to design trading systems that aren't vulnerable to such high levels of costs.

In the next part of the chapter I'm going to show you how to calculate the cost of trading a particular instrument at a given speed, and how to work out the likely costs you'll face. Then you'll see how to construct trading systems to ensure you won't be making more money for brokers and market makers, than for yourself.

Calculating the cost of trading
The cost of execution

The first kind of cost we'll analyse is execution cost. Back-tests nearly always assume that when executing a trade you will pay the mid-price. But in practice the difference between the mid and the price you achieve will depend on how large your trades are compared to the available volume. This difference is the execution cost. Look at figure 24, which shows a snapshot of the order book for the Euro Stoxx European equity index future. At this point the mid-price was halfway between the bid of 3,369 and the offer of 3,370; equal to 3,369.5.

Smaller traders can assume they will pay at most half the usual spread between bid and offer in execution cost, which is what you get from submitting a market order that crosses the spread and hits the best bid or offer. If you're selling 437 contracts or fewer then the price you'd receive is 3,369. Similarly if you're buying fewer than 8 contracts the most you would pay is 3,370. In this example the expected execution cost is 0.5 of a point (half of the one point spread between 3369 and 3370). If you placed limit orders you might do better, but it's better to be conservative and assume costs are higher than you'd hope.

This assumption is reasonable if your typical trade is less than the usual size available on the inside of the spread. Larger traders cannot assume this, and I discuss this further in the final part of this chapter. Also remember that this is not a book about high frequency trading. These assumptions are wrong if you are constantly submitting orders every few seconds or fractions of a second, as the order book will be affected by each of your successive trades.

FIGURE 24: ORDER BOOK FOR EURO STOXX INDEX MARCH 2015 FUTURES, AS OF 23 JANUARY 2015 11:13 GMT

Product | Product ID
EURO STOXX 50 Index Futures | FESX
Avg. Pr. | Cum. Qty. | Quantity | Bid
3,369.00 | 437 | 437 | 3,369.00
3,368.43 | 1,013 | 576 | 3,368.00
3,367.89 | 1,633 | 620 | 3,367.00
3,367.32 | 2,330 | 697 | 3,366.00
3,366.81 | 2,988 | 658 | 3,365.00
3,366.30 | 3,659 | 671 | 3,364.00
3,365.91 | 4,144 | 485 | 3,363.00
3,365.37 | 4,814 | 670 | 3,362.00
3,364.63 | 5,797 | 983 | 3,361.00
3,364.07 | 6,587 | 790 | 3,360.00
 | Contract | Last | Volume
 | Mar 2015 | 3,368.00 | 652,226
Ask | Quantity | Cum. Qty. | Avg. Pr.
3,370.00 | 7 | 7 | 3,370.00
3,371.00 | 540 | 577 | 3,370.99
3,372.00 | 1,147 | 1,724 | 3,371.66
3,373.00 | 696 | 2,420 | 3,372.05
3,374.00 | 647 | 3,067 | 3,372.46
3,375.00 | 1,017 | 4,084 | 3,373.09
3,376.00 | 831 | 4,915 | 3,373.58

Source: EUREX

Types of cost

The execution cost I calculated above is a key element of costs, but it's not the only one. There are also fees: commissions and taxes to pay. Here is a list of the types of cost you might face.

Expected execution cost per block | This is the execution cost you saw above; the difference between the mid-price and what you get when you actually trade. Smaller traders can usually assume they will pay at most half the usual spread between bid and offer, as in the 0.5 points for Euro Stoxx in figure 24. As a percentage of 3,370 this will be 0.01484%. To get the cost in cash terms multiply the percentage spread in price points by the value of each 1%.* For Euro Stoxx futures at a price of 3,370 this happens to be €337, so the execution cost is equal to 0.01484 multiplied by 3,370, which is €5.**
Fee per ticket | Many UK retail brokers impose a per trade commission regardless of the trade size. £5 to £15 is typical.
Fee based on trade size | Other brokers charge per 100 shares or single futures contract traded. My broker charges €3 per contract to trade Euro Stoxx futures.
Percentage value fee | Certain jurisdictions charge a percentage tax on the value of the trade, such as UK stamp duty at 0.5%. Some brokers also charge percentage commissions on larger transactions; 0.1% is typical.

* Remember this was defined in chapter ten, 'Position sizing', page 164, as the block value, the amount we make in cash terms when a price moves by 1%.

** For Euro Stoxx each one point move in the futures price costs €10. So a 1% move of 33.7 points is worth €337.

There may also be a holding cost for certain instruments. Futures, spread bets and contracts for difference require rolling over monthly or quarterly. Nearly all collective funds impose an annual charge. These holding costs are usually relatively small compared to trading costs, and they don't affect decisions about speed, so we'll ignore them.124

Standardising cost measurement

Suppose it costs €8 in total to trade one Euro Stoxx futures contract (€5 in execution costs and €3 in brokerage fees). Is this a lot? How does it compare with €5 to trade a German 2 year bond Schatz futures contract? Naively, €5 sounds cheaper than €8, but the answer is not as simple as you might expect. What if you have to buy 20 Schatz versus 10 Euro Stoxx to achieve the same amount of risk? (This is the volatility scalar from chapter ten, page 170.) Despite Schatz looking like a bargain it's going to cost you €100 versus €80 to put equivalent positions on, so Euro Stoxx is actually cheaper to trade.

This is another opportunity to use the technique of volatility standardisation. You should use a measure of costs that accounts for how risky different instruments are. The measure is defined as follows: if you buy one instrument block and then sell it, how much does that round trip cost when divided by the annualised risk of that instrument? This standardised cost is equivalent to how much of your annualised raw Sharpe ratio (SR) you'll lose in costs for each round trip.

To calculate it you take the cost to trade one block in instrument currency C, and double it because a round trip is two trades. You then divide by the annualised standard deviation of the value of one block of an instrument. This is the annualised version of the daily instrument currency volatility ICV (which was defined on page 168). Remember that to annualise daily volatilities you need to multiply by 16.125 So the standardised cost will be (2 × C) ÷ (16 × ICV).

An important implication of this formula is that the effective cost of trading is higher for instruments with lower price volatility. This is another reason to exclude very low risk instruments from your portfolio.

As I'm writing this, the price of the Euro Stoxx future has volatility of around 1.5% a day (the instrument riskiness defined on page 165), and as each 1% move is worth €337 (the block value I discussed on page 164) this equates to a daily standard deviation of the contract value of €506 (the ICV or instrument currency volatility). When I annualise this I get 506 × 16 = €8,096. Given the cost of trading at €8 per block, this is a standardised cost of 2 × €8 divided by €8,096, or 0.002 SR units.

Like most futures this is cheap to trade.126 Average standardised costs in 2014 for the futures contracts I traded ranged from around 0.001 SR for the most liquid like the FTSE 100, up to around 0.03 SR for Australian interest rate futures.127

Now let's look at a spread bet128 on the FTSE 100, where I am betting £1 per point. First I need to work out the instrument currency volatility.

Price volatility | Currently 0.75% a day.
Instrument block | £1 per point.
Block value | With the FTSE at 6600 a 1% move will be 66 points, the value of which at £1 per point will be £66.
Instrument currency volatility (ICV) | This is the price volatility multiplied by the block value: 0.75 × £66 = £49.50.

Now I can work out the costs.

Expected execution costs per block | Half the typical spread is 4 points, i.e. £4.* There are no fees or taxes.
Total cost per block (C) | £4
Instrument currency volatility (ICV) | From above £49.50.
Cost in SR units | 2 × C ÷ (16 × ICV) = 2 × £4 ÷ (16 × £49.50) = 0.01 SR

* This is for a quarterly forward bet - spreads on spot FTSE are tighter but with my typical holding period they would end up being more expensive.

This is about ten times larger than for the FTSE 100 future, which isn't surprising as the spread bet is a retail product with a smaller block size.129 Generally bets on most major indices come in around the 0.01 SR level, although those on individual shares will usually cost more. I'll use 0.01 SR as the benchmark cost for spread bets.

The third type of instrument we'll consider is exchange traded funds (ETFs). Like many equities, these are cheaper to trade in 100 share blocks. The precise cost will depend on volatility, and the volatility for ETFs depends on the underlying assets and whether any leverage is used. I will be conservative and check the cost of a relatively low volatility instrument, the iShares IGIL global inflation linked bond ETF, which is one of the ETFs I use in the asset allocator example in part four.

Price volatility | Around 0.43% a day in early 2015.
Instrument block | 100 shares.
Block value | 100 shares at $144 per share is $14,400. 1% of this is $144.
Instrument currency volatility | This is the block value multiplied by the price volatility: $144 × 0.43 = $62

Now for the costs.

Expected execution cost per block | The typical bid offer on this ETF is 70 cents wide or 0.486% of the current price of $144. The block value is $144. So if I pay half the spread I'd pay 0.486 × $144 × 0.5 = $35 for each block.
Fee per ticket | My broker charges me $5.00 per trade. I assume there are no other fees or taxes due.
Total cost per block (C) | $35 + $5 = $40
Instrument currency volatility (ICV) | $62 (from above).
Cost in SR units | 2 × C ÷ (16 × ICV) = 2 × $40 ÷ (16 × $62) = 0.08 SR

ETFs with higher price volatility, such as equities, will cost less than this on a risk normalised basis, but to be safe I'll use the figure of 0.08 SR as my expected cost for ETFs. The costs in these examples are correct given current market conditions and the brokerage fees I'm paying, but you should calculate your own figures before making any decisions.

Introducing turnover

What is the point in knowing it will cost us 0.08 Sharpe ratio (SR) units, 0.01 SR or 0.002 SR, to buy and sell a risk adjusted amount of each instrument? It's pointless having just a standardised measure of costs; you also need a standardised measure of how quickly you're trading. Since you know the cost per round trip in annualised SR units you'll need to count the number of round trips done annually, where a round trip is a buy and then a sell.

I measured standardised costs by making them volatility standardised. Similarly each buy and sell should be of a volatility standardised quantity of instrument blocks. Because of the way the framework works, this is equivalent to your expected average absolute position, or the position you'd have with an average sized forecast (defined as the volatility scalar in chapter ten, page 170).

The number of round trips per year is the turnover. A turnover of 1 unit means you expect to do one buy and one sell of an averagesized position per year; so your average holding period will be 12
months. Similarly a turnover of 52 units would imply you're
hanging on to positions for an average of one week. Because
turnover is volatility standardised it means you can consider the
trading pattern of each instrument in isolation (the so called
trading subsystem that was defined in chapter ten), without
worrying about the rest of your portfolio.

For example suppose it costs a standardised 0.01 Sharpe ratio units
for each round trip in spread bets, and your turnover is 10 units of
average position each year. Then over a year of ten round trips (ten
buys and ten sells), you'd lose 10 × 0.01 = 0.10 SR in costs. That
means an SR of 0.5 would be reduced to 0.5 - 0.1 = 0.4.

Where does turnover come from?

Before continuing you also need to understand where turnover
comes from. For what reasons would you want to trade? Here's a
list, in order of descending importance.

| | |
|---|---|
| Forecast | A change in forecast from one or more of the trading rules used by staunch systems traders, or because a semi-automatic trader is placing new bets or closing old ones. This is the main source of position changes, except for asset allocating investors for whom forecasts do not change. |
| Instrument currency volatility | Movements in the expected daily standard deviation of the value of each instrument block (price volatility multiplied by block size). This is the second most important reason for position changes. |
| Trading capital | Changes in the amount of capital you currently have at risk. This is determined by your profits and losses and by any additional funds you add or withdraw. Ignoring withdrawals and injections of money, with the highest recommended 50% volatility target, this will change by an average of 3% each day.<br><br>You can't reduce the trades that result from this component, except by using a lower percentage volatility target. So with a target of 16% it would move by around 1% a day. |
| Exchange rate | This is the exchange rate between an instrument's currency and the currency your current trading capital is in. Rates usually move by less than 1% a day in major currencies.<br><br>You can't reduce these trades, which in any case are relatively small. |
| System parameters | These are parameters in the trading system which should only change infrequently if at all: Forecast weights, Instrument weights, forecast and instrument diversification multipliers, and the percentage volatility target.<br><br>You can eliminate the trades that result from this element by not meddling with your system! |

In the rest of this chapter I will focus on how forecasts and changes
in price volatility influence trading speed, since these can readily
be adjusted and have the biggest effect.

Estimating the number of round trips

You can now calculate the expected costs of trading each
instrument, given the units of turnover of the trading system and
the standardised costs. But how do you find the turnover? There
are three ways to estimate it.

| | |
|---|---|
| Sophisticated back-test | If you have access to decent back-testing software, or can write your own, then you can include a function that estimates turnover directly. |
| Simple back-test | More rudimentary back-testing tools can give you an estimate of the average number of instrument blocks traded each year and the average absolute number of blocks you held. You can then calculate turnover as:<br><br>Average number of blocks traded per year ÷ (2 × average absolute number of blocks held) |
| Rule of thumb | The third alternative is to use rules of thumb. This approach is fine for semi-automatic traders whose turnover will depend on the tightness of their stop loss, asset allocating investors who don't get turnover from forecast changes, and for those staunch systems traders who are using only the trading rules I provided in chapter seven (the carry and EWMAC rules).<br><br>There will be relevant rules of thumb later in this chapter and in the example chapters of part four. |

Using trading costs to make design decisions

Setting a speed limit

Let's return to the Euro Stoxx future, which had a standardised cost
of 0.002 Sharpe ratio (SR). Suppose you have a rule with a back-
tested pre-cost return of 0.40 SR, and a turnover of 50 round trips
per year. You'd expect to pay 50 × 0.002 = 0.10 SR annually in costs
and receive 0.30 SR of net performance.

What if you had an alternative rule, with a turnover of 100, but
with a pre-cost return of 0.60 SR? Though your costs have doubled
to 0.20 SR, the net return has increased to 0.40 SR. Surely you
should choose the more expensive option?

In chapter three when I discussed fitting I pointed out that there is
always considerable uncertainty about expected pre-cost
performance. An implication of that is you need a lot of historical
data to prove that a trading rule variation is likely to be profitable
(as shown in table 5 on page 71), let alone make enough money to
cover its costs.

It also means you need a lot of data to make it probable that one
trading rule had better performance in the past than another. So
considerable evidence is required to justify trading a faster, and
apparently superior, variation rather than a slower, cheaper and
supposedly inferior alternative (see table 6 on page 73).

The relative pre-cost Sharpe ratio you will achieve in practice is
extremely uncertain, whilst expected costs can be predicted with
much more accuracy. There is one further danger in blindly
accepting the back-test results of expensive systems. What I've
shown you in this chapter is an estimate of current costs, which
could be very different from what they were 20 years ago. In many
markets trading costs were much higher in the distant past than
they are now.

A fast trading rule might look great in the past, but if the market
was very expensive nobody could have actually exploited it. Now
costs have fallen there is a good chance the effect will vanish.

To ensure you don't chase performance, or trade faster than was
viable in the past, I recommend that you set a speed limit; a
maximum expected turnover you will allow your systems to have.

At the start of this chapter I said I wouldn't trade a strategy which
paid two-thirds of its profits out as costs, amounting to 1.0 in SR
annually. I personally think it's foolhardy to pay more than a third
of your expected profits in trading costs and I use that to set my
own speed limits. If you're being realistic then the Sharpe ratio
from trading each instrument using its trading subsystem is
unlikely to be higher than 0.4 on average.130

This implies you should never pay more than a third of 0.4, or 0.13
SR, in costs, regardless of how good your back-test is. Remember
that cost in SR terms is equal to the standardised cost multiplied by
the turnover in round trips per year. So dividing 0.13 by the
standardised cost of an instrument will give you the turnover speed
limit for that instrument.

For a relatively cheap futures market like the Euro Stoxx this
implies a maximum turnover of 0.13 ÷ 0.002 = 65 round trips per
year, or an average holding period of just under a week. With the
very cheapest instruments like NASDAQ futures you might be able
to double that turnover to give a holding period of a couple of days.

However this precludes day trading, which with two or more round
trips per day would be a turnover of at least 500 round trips each
year. To trade that fast without spending more than a third of your
returns on costs you'd need to get a significantly higher pre-cost
Sharpe ratio, or reduce your standardised cost to around 0.13 ÷ 500
= 0.00025 SR units. That level of costs is around a quarter of what
the cheapest futures can achieve.

As it happens about a quarter of the standardised costs of these
super cheap futures are commissions of around $1 per contract,
with the rest coming from execution costs. So to day trade you'd
need to get your execution costs down to zero, which means
consistently achieving the mid-price or better. To trade even faster,
with three or more round trips a day, you'd have to be getting
consistently negative execution costs.

In conclusion then, to day trade even the cheapest instruments you
will need to achieve very high pre-cost Sharpe ratios, or have an
execution strategy that consistently captures the spread. This isn't
impossible, but clearly only those with a proven record of
achieving these goals should contemplate trading this quickly. This
capability is relatively rare in practice, which is why the vast
majority of amateur day traders are unprofitable.

With a cost of 0.13 SR a year if you're using the maximum
suggested 50% volatility target (as defined on page 146 in chapter
nine), then you'll be paying 0.13 × 50% = 6.5% a year in costs. This is
a reasonably large drag on performance and personally I wouldn't
want to see anything bigger.

As discretionary semi-automatic traders can't use back-tests they
need to avoid over-confidence about their performance
expectations. Rather than a maximum Sharpe ratio (SR) of 0.40 on
each instrument, you should conservatively expect to get at most
0.25 SR.131 This implies paying no more than a third of 0.25, or 0.08
SR in costs annually. Asset allocating investors, whose static trading
systems will have similar performance to the underlying assets,
should also use this lower figure.

You're now ready to think about how you can customise your
trading systems with an understanding of costs. There are several
areas in the framework where performance expectations are used.
These decisions should now be made using costs as well as
expected pre-cost performance.

| | |
|---|---|
| Which instruments to trade | It's going to be difficult to trade instruments with costs which are too high for the kind of system we want to use. |
| Deciding average holding period by setting stop losses (semi-automatic traders) | Semi-automatic traders should use stop losses which target a particular average holding period for positions. When setting the level of these stops you need to consider the costs of your preferred instruments. |
| Selecting, fitting and calibrating trading rules (staunch systems traders) | If you decide to fit your trading rules then you must consider both pre-cost Sharpe ratio and costs. Remember that you have more certainty of costs than of pre-cost performance.<br><br>With my preferred method of fitting you shouldn't look at pre-cost performance but should still exclude trading rule variations whose likely costs will be too high. |
| Setting forecast weights (staunch systems traders) | You need to use likely costs to avoid overweighting trading rule variations which perform well but are also relatively expensive to trade. |
| Setting the risk percentage | When checking your Sharpe ratio to set the risk percentage, you should use after-cost performance. |
| Setting the look-back for estimating price volatility | After forecast changes this is the next key source of turnover in your trading systems. The costlier your trading is, the slower you should update your estimate of price volatility. |
| Allocating instrument weights (semi-automatic traders and asset allocating investors) | You should consider giving less weight to more expensive instruments, unless you think additional pre-cost performance compensates you. |

Which instruments to trade?

There are two routes to take when designing your trading systems
so that they don't exceed any speed limits. Firstly you could decide
what sort of speed you wish to trade at and then choose
instruments that are cheap enough to trade that quickly.
Alternatively if you have a preference for particular instruments
then that will limit how fast you could trade them. So for example if
you can't trade futures and prefer ETFs, then that will heavily
curtail your trading speed.

If you use my recommended maximum of 0.08 Sharpe ratio (SR)
units paid annually in costs for asset allocating investors and semi-
automatic traders, then table 34 gives the maximum possible
standardised cost for a given holding period and turnover. It also
shows instruments which typically have that level of cost. You can
then infer which instruments to trade for a given speed of trading,
or how quickly to trade given a preferred set of instruments.

The table also shows the lower limit on how slowly you can trade a
particular kind of system, with a minimum achievable turnover in
round trips per year. Given your limit on what you're willing to pay
in costs, you can imply from this turnover which instruments will
be too expensive to trade at all.

TABLE 34: WHAT SPEEDS AND HOLDING PERIODS CAN SEMI-AUTOMATIC TRADERS
AND ASSET ALLOCATING INVESTORS TRADE WITH PARTICULAR INSTRUMENTS?

| Holding period | Typical turnover | Maximum cost SR | Likely instruments | |
|---|---|---|---|---|
| 1 day | 256 | 0.00031 | None | |
| 3 days | 85 | 0.001 | Cheapest futures, e.g. NASDAQ | |
| 1 month | 12 | 0.0067 | Nearly all futures except short maturity bonds, STIR* | |
| 6.5 weeks | 8 | 0.01 | Index spread bets, e.g. FTSE | |
| 3 months | 4 | 0.02 | Individual equity spread bets | |
| 6 months | 2.0 | 0.04 | Cheapest ETFs, e.g. equity indices | Slowest semi-automatic trader |
| One year | 1.0 | 0.08 | Benchmark inflation linked bond ETF | |
| 2.5 years | 0.4 | 0.20 | Most individual equities | Slowest asset allocating investor |

The table shows for different holding periods the turnover in round trips per
year, maximum instrument cost if we pay no more than the recommended 0.08
SR a year, and typical instruments at each cost level (estimates as of January
2015).

* Short term interest rate futures

Asset allocating investors can get down to an annual turnover of
0.40 round trips per year, implying that a cost of 0.08 ÷ 0.40 = 0.20
SR is affordable.132 So ETFs, which we estimated will cost at most
0.08 SR, will be fine. As I explain in the next section, semi-automatic
traders with very wide stop losses will realise a turnover of 2.0
round trips a year. A cost of 0.08 ÷ 2.0 = 0.04 SR is the maximum
they could pay. This rules out ETFs but allows spread bets, which
we costed at 0.01 SR.

I've done a similar analysis for staunch systems traders, for whom I
recommend a maximum of 0.13 SR units of cost per year. Table 35
gives the figures and I've also shown how each level of turnover
relates to the trading rules I presented in chapter seven, 'Forecasts'.

TABLE 35: WHAT SPEED SYSTEMS CAN STAUNCH SYSTEMS TRADERS USE?

| Typical turnover | Maximum cost SR | Likely instruments | |
|---|---|---|---|
| 128 | 0.001 | Cheapest futures, e.g. NASDAQ | |
| 54 | 0.0024 | Average future, e.g. WTI Crude | Fastest single trend following rule I use (this the EWMAC 2, 8 rule)* |
| 28 | 0.0046 | Most futures except short end bonds, equity volatility indices, STIR | Second fastest single trend following rule (this is the EWMAC 4, 16 rule) |
| 12.5 | 0.01 | Nearly all futures, index spread bets | Set of rules used in chapter 15 |
| 7.5 | 0.017 | Cheaper individual equity spread bets | Slowest trend following rule I use (this is the EWMAC 64, 256 rule) |

The table shows for different levels of turnover in round trips per year the
maximum standardised instrument cost if you pay no more than the
recommended 0.13 SR a year for staunch systems traders, and typical
instruments at each cost level (estimates as of January 2015).

* Defined in chapter seven, 'Forecasts', and appendix B (page 294).

I've also shown the level of turnover that you'll get with the set of
trading rules that I advocate using in chapter fifteen, where I
explain in detail the design of the staunch systems trader example.
Staunch systematic traders who use this recommended set oftrading rules, which is fairly slow, will get a turnover of 12.5 round trips per year.133 You'd get a maximum standardised cost of 0.13 ÷ 12.5 = 0.01 SR, which is fine for nearly all major futures markets and index spread bets.

Deciding average holding period by setting stop losses

Semi-automatic trader

How should semi-automatic traders determine how quickly to trade? You might think it depends on how trigger happy you are, with itchy fingered day traders clicking in and out every few minutes, and relaxed macro traders trading every few weeks or months.

But I advocate that traders exclusively use a systematic stop loss to exit positions, no matter how they decide to enter them. This means the average holding period will depend mainly on how tight, or loose, your stops are set. You should then ensure that your trading style, and the horizon you are trying to predict price movements for, is in line with your stop levels.

If stops are set very tight then you'll have short holding periods and high turnover. You won't be able to trade more expensive instruments with tight stops, since with a speed limit on what you're willing to pay in Sharpe ratio (SR) costs there will be a maximum viable standardised cost.

Table 34 shows that with the cheapest futures you can use a relatively tight stop, with a holding period of three days. However this would be far too expensive if you're using spread bets. I mentioned a particular spread betting system in the introductory chapter which held positions for around a week. This would have a turnover of 52 round trips per year. The standardised cost I'm using for spread bets is 0.01 SR, so this gives costs of 52 × 0.01 = 0.52 annually.

Earlier (page 160) I calculated the implied volatility target of that system at 160%. This implies you'd need to make 0.52 × 160% = 83% a year on your trading capital before costs – just to break even!

Table 34 shows that with spread bets you can't use stops with holding periods of less than about six weeks. Furthermore it's unlikely that any trader will be happy with a holding period of more than six months. So the slowest turnover you can get is 2 round trips a year, which is the figure I used earlier in the chapter when looking at instrument selection.

Selecting trading rules

Staunch systems trader

In chapter three I said I don't like to fit or calibrate trading rules using real performance. But that prohibition only applies to pre-cost performance. I positively encourage you to back-test and find the expected turnover of your trading rules and then reject variations which are too expensive.

Using my recommended guideline for setting speed limits from above you don't want costs greater than 0.13 Sharpe ratio (SR). So you should be rejecting trading rules with turnovers greater than 130 round trips per year for the very cheapest futures (cost 0.001 SR for each unit of turnover), over 65 round trips for the Euro Stoxx future (cost 0.002), and with turnovers over 13 for a spread bet with a standardised cost of 0.01 SR.134

It is simplest to use the same trading rules and variations for all the instruments you trade. This means you will need to drop any rules which are too fast for the most expensive instrument you have; remaining rules will automatically be fine for the cheaper ones. You'll see how this is done in more detail in part four, chapter fifteen, which is the example chapter for the staunch systems trader.

However if the set of instruments you have features trading costs that vary significantly you might consider using faster variations only with the cheapest instruments, and using a slower set of variations for the expensive ones. Costs in my own portfolio vary by a factor of 40 across the futures that I trade, so this is the approach I use.

Trading slower rules – Weights to trading rules

Staunch systems trader

How should you determine the forecast weights to use when forming a combined forecast? Unless you think that faster rules will give you a pre-cost Sharpe ratio (SR) advantage which compensates for their costs you’re going to have less weight on higher turnover rules, especially in instruments which are expensive to trade.

If you use bootstrapping to determine weights on a rolling out of sample basis then you can include a correction for costs in estimates of returns. Bootstrapping will automatically determine the right weights, accounting for predictable costs and uncertain profits. By comparing the weights found when pooling results across the portfolio with those from individual instruments it will also tell you if different forecast weights make sense, or if you should use the same weights.

Personally I’ve never found consistent evidence in my own system that faster trading rules, whether in general or as variations of a single rule, have a higher pre-cost Sharpe ratio (SR).135 So if you’re deciding weights using handcrafting then I recommend that you assume the same pre-cost SR for all trading rules, but account for their different trading costs. You can then adjust forecast weights for trading rules based on your estimate of the SR of costs, as we did in chapter four on page 96.

How do we do this?

Remember from chapter four that the adjustment is done by comparing the SR of an asset versus the average across the portfolio. For each instrument and trading rule variation, you should use the cost per round trip and the turnover to calculate the total cost in SR units per year. If you’ve decided to keep the same set of trading rules for all instruments you may want to use the same adjustments on every instrument, which means using the highest and most conservative instrument standardised cost to do your adjustment, rather than the specific cost for each instrument.

On a given instrument you should then take the average cost in SR points over all rules you are finding weights for. Because costs are fairly predictable you should use column A ‘With Certainty’ of the SR adjustment table 12 in chapter four (page 96). As an extreme example, if you think that a particular rule is going to cost 0.13 SR per year, versus an average for all rules of 0.03 SR, then the performance difference is 0.10 SR worse than average and you should multiply its weight by 0.95.

With my recommended speed limit applying to exclude any trading rules with costs of more than 0.13 SR, the adjustments made here will never be larger than 0.95 or 1.05. In most cases they will be much smaller and not worth bothering with. However if you’re using a higher speed limit then adjusting for trading rule costs could significantly alter your weights.

More conservative estimation of Sharpe ratio to set risk percentage

This section is relevant to all readers

Back in chapter nine, ‘Volatility targeting’, I said that you should have realistic expectations of likely Sharpe ratio (SR) to determine the optimal level of risk to take. If you’re doing your own back-test, or estimating your likely performance in some other way, this needs to be done on an after-cost basis.

Alternatively if you’re using the suggested figures for Sharpe ratio in the relevant chapters of part four, then there’s nothing more to do as all these assumptions are post-cost.

Slower estimation of price volatility

This section is relevant to all readers

After forecasts the next source of turnover is the adjustment of positions to cope with changes in the risk of each instrument – the instrument currency volatility, which I defined on page 168. This in turn depends on how quickly you update your estimate of the standard deviation of daily percentage returns, the price volatility,

which was also defined in chapter ten.

I mentioned three ways of estimating price volatility in that chapter. Two of these methods involved formally calculating the standard deviation of price changes over a volatility look-back period, either with a moving average or an exponentially weighted moving average (EWMA). I suggested that these should be used by asset allocators and staunch systems traders, with a default look-back of 25 business days, or 36 days with an EWMA. The other method involved eyeballing the chart, which I recommended for semi-automatic traders.

Asset allocating investor

Staunch systems trader

If you’re measuring price volatility using a simple moving average, or the equivalent exponentially weighted EWMA, should you use my recommended look-back of 25 days (five weeks of trading days), or a slower look-back of ten, or even 20 weeks? On page 168, figure 23 showed that slower look-backs are very sluggish to react to changes in risk. My research suggests that look-backs over 20 weeks lead to much poorer trading system performance. However faster look-backs change very frequently and will generate additional turnover and thus cost more to trade.

First let’s quantify the effect of higher costs. You need to check the turnover for each trading subsystem. This is all the trading that you’ll be doing for a particular instrument. It will be what you get from any changes in forecasts, plus additional turnover as your estimate of price volatility changes. You can ignore the other reasons for trading that I discussed earlier, as these are relatively unimportant.

If you have multiple trading rules then you need to work out the trading coming from your combined forecast across all trading rules. To get this first take the weighted average, using forecast weights, of the turnover in round trips per year for each individual trading rule. Then multiply this by the forecast diversification multiplier to get the turnover of the combined forecast.

If you’re an asset allocating investor using the ‘no-rule’ rule of a constant forecast then there are no forecast changes and you’ll have a zero turnover from trading rules.

You then need to apply a correction for the effect of changing your estimate of price volatility, which always increases turnover. At the same time, you must also account for the effect of position inertia, which I introduced on page 184 – not trading any position change greater than 10%. This slows trading down.

You can see the net result of these two corrections in table 36. The table shows that changing the look-back has almost no effect if the turnover of the original combined forecast is five or more round trips per year. So if you’re trading fast trading rules, on cheap instruments, then you can safely use the default look-back.

For slower rules it will depend on the precise costs of your instruments. Take the ‘no-rule’ rule used by asset allocating investors. As before let’s assume you’re trading ETFs with a standardised cost of 0.08. With zero turnover in forecasts you should refer to the top row of the table. Using the default five week look-back to estimate price volatility gives a turnover of 1.6 round trips per year. You’d have costs of 1.6 × 0.08 = 0.13 Sharpe ratio (SR) units annually. This violates the recommended speed limit of paying 0.08 SR in costs for asset allocating investors, who are unlikely to see high performance from their static portfolios.

In contrast with a 20 week look-back, giving a turnover of 0.40, you’d only pay 0.40 × 0.08 = 0.032 SR. This is a quarter of the original cost, saves a substantial 0.10 SR units, and is well within the speed limit. Notice that a turnover of 0.4 round trips per year is the lowest an asset-allocating investor can achieve without slowing down their estimate of price volatility beyond the maximum recommended 20 weeks.

TABLE 36: WHAT EFFECT DOES SLOWING DOWN YOUR ESTIMATE OF PRICE VOLATILITY HAVE? A SLOWER ESTIMATE CAN REDUCE FINAL SYSTEM TURNOVER, IF UNDERLYING TRADING RULES ARE ALSO SLOW

Starting turnover of trading rules | Look-back of price volatility estimate*
| 20 weeks | 10 weeks | 5 weeks
0 (no-rule rule) | 0.4 | 0.8 | 1.6
1 | 1.2 | 1.5 | 2.5
5 | 4.7 | 5.0 | 5.7
10 | 9.4 | 9.8 | 10.2
12.5 | 11.7 | 12.2 | 12.6
20 | 19.1 | 19.2 | 19.7
40 | 39.2 | 39.2 | 39.4
60 | 60 | 60 | 60

The table shows the final turnover, in round trips per year, we get from changing the look-back for price volatility (columns) given a starting level of turnover from trading rules (rows). Five weeks (25 business days) is the default look-back. Starting turnover is the average turnover of your trading rules, weighted by forecast weights, multiplied by forecast diversification multiplier. Position inertia is used to slow down trading.

* Using a simple moving average. For an exponentially weighted moving average the relevant look-backs are 144 days instead of 100 days, 72 days instead of 50 days, and 36 days instead of 25 days.

Semi-automatic Trader

The first method of estimating price volatility I discussed in chapter ten was eyeballing; looking at the chart and figuring out what a typical daily move was. It’s obviously very difficult to back-test this method as everyone’s perception is different. However you should usually use a one month window on a chart to find the price volatility, since this will give similar results to the 25 day volatility look-back I recommended for more formal moving average methods. This is fine if you’re trading cheap instruments like

futures.

With more expensive assets, like spread bets and ETFs, then I’d suggest you still use a one month window. However I would recommend that you also compare your estimate of the cash risk of an existing position (the instrument currency volatility defined on page 168) to the value you had yesterday. If the estimate hasn’t changed by more than 25% from its last value then don’t bother to adjust it.

Just like position inertia this will reduce any trading caused by updating the volatility estimate on existing positions and keep your costs down. However when opening new positions you should use the most up-to-date estimate of volatility to work out your initial trade size.

Choice of instrument weights

Asset allocating investor

Staunch systems trader

This isn’t relevant to semi-automatic traders who don’t trade a fixed set of trading subsystems.

Suppose you’re running a portfolio including a cheap instrument like a Euro Stoxx future, and a more expensive one like two year German bond (Schatz) futures. Perhaps you’ve managed to find trading rules that make sense for each instrument and fitted some forecast weights to them; or you could be an asset allocating investor who is going to use the single ‘no-rule’ rule with a constant forecast. As in chapter eleven you must now allocate your trading capital and think about the appropriate instrument weights to give to each of these two trading subsystems.

Will you get lower after-cost performance from running trading systems for the more expensive Schatz? If so then you should obviously give it a lower instrument weight. But this is not a clear-cut decision. Academic research shows that the extra costs of owning less liquid instruments are often outweighed by higher profits, such as the additional returns you get from investing in the

equities of smaller firms. As I briefly mentioned in chapter two, ‘Systematic Trading Rules’, we tend to get rewarded for being exposed to illiquid assets.

My own research shows that more expensive instruments usually perform somewhat better even once costs are taken into account; but only if they’re traded relatively slowly, with a turnover of less than 15 round trips per year. The improvement isn’t usually strong enough to warrant a higher allocation, but it does mean that under-weighting costly instruments doesn’t make sense. For asset-allocating investors (whose turnover from table 36 will be at most 1.4), and slower staunch systems traders, there is no need to consider adjusting instrument weights in light of costs.

If you’re a fast systems trader, with a turnover of more than 15 round trips per year, then my research shows that you will see worse relative performance after costs for expensive instruments. However if you’ve followed the advice I gave earlier then you wouldn’t be trading them that quickly anyway, since you’d be breaking the speed limits implied by the recommended limit of 0.08 Sharpe ratio (SR) units or 0.13 SR units, per year spent on costs.

When you stick to the speed limit then only the very cheapest instruments would have access to quick trading rules. So in general you’d either be trading cheaper instruments more quickly than expensive ones, or trading all your instruments at the same relatively slow pace. In my own research into systems with these features I don’t find any difference in after-cost returns between instruments, regardless of their standardised costs.

In conclusion, unless bootstrapping tells you differently, I would recommend assuming the same post-cost SR for all trading subsystems. If you’re using handcrafted instrument weights this means no Sharpe ratio adjustment is needed to account for different cost levels.

Trading with more or less capital

This section is relevant to all readers

Trading with a lot of capital

Let’s have another look at the order book in figure 24. An investor who wants to sell 437 contracts or fewer can assume they will pay at worst half the spread, 0.5 price units, as they’re selling at 3,369 compared to the mid-price of 3,369.5. But a large hedge fund which needs to sell more than this, like 5,000 lots, has a problem.

They have three options when they submit the order. Firstly they can cross the spread and submit a single market order. They will get 3,369 for the first 437 lots, but the next 576 lots will go for 3,368, then 620 at 3,367 and so on. The average price received per lot will be 3365.2, which compared to the original mid of 3,369.5 gives an execution cost of 4.3 points. The exact cost for any given trade will depend on the depth of the order book when it is submitted.

Secondly they can offer 5,000 lots at 3,370, adding to the 7 lots already on the order book. They might get lucky and meet a large buyer who takes their offer. This would beat the mid-price by half a point, and get an effectively negative execution cost. But it’s much more likely that on seeing this huge order other traders will push the price down, leaving the order unfilled and the market at a worse level.

Finally the funds human traders or execution algorithims can break the order up into chunks and execute it gradually. The order will take longer to execute and there will be a lot of uncertainty about the fill level, and even if each chunk is small other market participants will see the individual orders coming through and react accordingly, which will probably result in the price drifting down.

In none of these three cases is the execution cost guaranteed to be exactly 0.5 points. If you are trading in large size, in relatively illiquid markets and relatively quickly, you can’t casually assume you will pay half the spread. If your typical order size is going to be greater than the usual depth available at the inside spread, you need to do serious research to calculate your expected trading costs, and to work hard at optimising your execution.Trading with relatively little capital

Those with much lower fund values have a different problem.
Think back to the example in table 32 on page 183. The imaginary
investor there had a €100,000 annualised cash volatility target, and
after working out the target positions they needed to short 2.62 S&P
500 futures contracts, based on the combined forecast of -10. But
what if you are an amateur investor with only €40,000? Running at
the maximum recommended 50% percentage volatility target
would give you a mere €20,000 cash volatility target. With one-fifth
of the risk you'd get one-fifth of the target position. However you
can't short the 0.524 contracts this equates to. You'd have to short a
rounded position of just one contract.

With a €20,000 volatility target if your S&P 500 combined forecast
doubles from -10 to -20, you'd still be short just one contract.136
With a forecast of -20 if the price volatility then doubled, you'd still
have just the single short.137 Your risk is much 'lumpier' than if you
could trade fractional contracts. The problem occurs because the
minimum size of the S&P future is quite big.138

As I explained in chapter six, 'Instruments', the minimum block
size is relatively large for many other instruments. Equities with
very high prices – like Berkshire Hathaway A shares, currently
trading at $220,000 each – are obviously going to be an issue, whilst
UK spread betting firms may not allow you to trade in bets of only
£1 per point on some indices.

Apart from the S&P, many other futures contracts tend to have
large nominal values including long maturity bonds, CME currency
futures, and some energy and agricultural commodities. An
extreme example is the Japanese 10 year bond future which
currently has a price of around 150 million yen, or $1.3 million. In
some cases there are mini versions of these large contracts, but
these might not be liquid enough.

Even without a large minimum it may be impractical or
uneconomic to trade small sizes. With a per ticket cost of €4 to buy
ETFs it doesn't make sense to buy in blocks of less than 100.

To find out where you could have minimum size problems you
need to work through the calculations in earlier chapters, assuming
the maximum combined forecast. This will give you the highest
possible position for an instrument given the current level of
volatility. My recommended maximum absolute forecast of 20 will
give you a maximum position of 2 × volatility scalar × instrument
weight × instrument diversification multiplier.

Staunch systems traders will need to check this for every
instrument they are trading. Semi-automatic traders should do the
same calculation for any instruments they are planning to place
bets on. Asset allocating investors, whose forecast is always a
constant +10, should use half of the usual figure to get their
maximum position: 1 × volatility scalar × instrument weight ×
instrument diversification multiplier.

Let's check the result for the example we're using. In table 31 (page
182), the volatility scalar for the S&P 500 was 7.43. This was
calculated with a €100,000 cash volatility target, so with a €20,000
volatility target it will be one-fifth the size. Hence the volatility
scalar with a lower account size is one-fifth of 7.43, or 1.49. From
table 32 the instrument weight is still 25%, and the diversification
multiplier 1.41, so the maximum possible position then is 2 × 1.49 ×
25% × 1.41 = 1.05. This is clearly too low. No matter what happens
the position will be long or short one contract (or none).

It is a matter of judgment as to what kind of maximum position
you'd find acceptable. My recommendation is to be satisfied with a
maximum possible position of four or more instrument blocks. If
you can't get to this level you will need to consider taking one of the
following steps.139

| Increase weight to instrument (only in moderation) | If instead of 25% you put 100% of the example portfolio into the S&P 500 then your maximum position would be a slightly more reasonable 3 contracts.* However any increase in weight will have to come from other instruments hence moving instrument weights away from their optimum, unless you also take the next option. |
| Reduce overall portfolio size | It's better to increase the instrument weight by reducing the number of instruments you have, but still using the correct bootstrapped or handcrafted weights. However this still reduces diversification. I'll go into more detail about determining the ideal portfolio size in the next section. |
| Remove instrument | If the instrument size is unreasonably large, and you will need to significantly reduce the total number of assets in your portfolio to accommodate it, then you should exclude it. |
| Live with it | You might have a large portfolio with just a few instruments where size is a problem. For example half a dozen of the futures contracts in my own portfolio of more than 40 have maximum positions of less than four contracts. On average my portfolio risk and return is about right, even if it is lumpier than I would prefer on individual instruments. However I still require that maximum positions are at least one instrument block, or there is clearly no point including the relevant asset. |

* The instrument weight goes from 25% to 100% and the instrument diversification multiplier
falls from 1.41 to 1, as there's only one instrument. The former increases the maximum
position, the latter reduces it but by less. The new maximum position calculation is 2 x 1.49 x
100% x 1.0 = 2.98.

Determining overall portfolio size

Asset Allocating Investor
Staunch Systems Trader

Given that small account sizes present problems, how would an
asset allocating investor with a few thousand euros decide how
many of the thousands of exchange traded funds to hold? How does
a staunch systems trader without millions of dollars in trading
capital work out which of the 200 or so liquid futures contracts
they should trade?

The principle you should follow is to hold the most diversified
portfolio possible without running into any problems with
maximum positions. Ideally you want at least one instrument from
each major asset class. For each asset class you should choose
instruments that don't give you a maximum position that is too
small; as I said above my recommendation would be to avoid
anything with a maximum of less than four instrument blocks.

You then only add additional instruments to an asset class if this
doesn't cause a small maximum position problem to appear either
in the new instrument or in an existing one. You should also
consider costs and the other characteristics which I discussed in
chapter six, 'Instruments'. You'll see examples of constructing these
portfolios in the relevant example chapters fourteen and sixteen, in
part four.

Semi-automatic Trader

Semi-automatic traders generally have smaller portfolios, and these
are of an ad-hoc group of instruments, rather than the fixed set
used by others. But you should still check you have no issues with
low maximum positions on anything you're likely to trade, for
example by using my recommendation to have at least a four block
maximum position.

Remember from chapter eleven, 'Portfolios', (page 179) that your
portfolio weights are 100% divided equally by the maximum
number of bets you're likely to make, so adjusting instrument
weights is not an option for dealing with size problems. So if you
have problems you should consider reducing the size of your
portfolio by lowering the maximum number of bets, or not trading
that instrument.

Summary of tailoring systems for costs and capital

Standardised cost estimate

| Cost to trade one block | Execution costs: Half the bid-offer spread except for those with large account sizes, dealing in illiquid markets or with very fast trading. Fixed fees per ticket. Fixed fees per position unit traded. Percentage value fees and taxes. The total cost to trade an instrument block should be calculated in the same currency as the instrument's value. |
| Instrument currency volatility | The expected daily standard deviation of the value of one instrument block in the currency of the instrument, as calculated in chapter ten, 'Position Sizing', (page 168). |
| Standardised cost | Annualised cost in Sharpe ratio (SR) per round trip (buy and sell): Twice the cost to trade one block divided by annualised instrument currency volatility (daily instrument currency volatility multiplied by 16). |

Calculating cost of trading rules and trading subsystems

| Approximate turnover from a back-test | To calculate the standardised turnover in round trips (buys and sells) per year: (Number of instrument blocks traded per year) ÷ (2 × average absolute number of blocks held) |
| Turnover for systematic trading rules | Calculated from back-test or implied from rules of thumb. Rules of thumb for my suggested trading rules explained in chapter seven, 'Forecasts', are available in the relevant example in chapter fifteen. |
| Cost of trading rule for instrument | Turnover for trading rule, in round trips per year, multiplied by standardised cost for instrument. |
| Turnover from forecast changes | Staunch systems traders: Can get this from back-test, or by taking a weighted average, using forecast weights of trading rule turnovers, multiplied by forecast diversification multiplier. The turnover of the 'no-rule' rule used by asset allocating investors is zero. Semi-automatic traders should use the turnover implied by the holding period which is determined by their stop loss, from table 34. More detail is given in chapter thirteen. |
| Turnover for trading subsystem | The turnover from forecast changes is corrected for the look-back used to estimate price volatility and position inertia, using table 36. |
| Cost of trading subsystem | Turnover for trading subsystem multiplied by standardised cost for instrument. |

Taking action to cope with costs

| Speed limit | I recommend that the costs of an instrument's trading subsystem should be at most one-third of a conservative estimate of the pre-cost Sharpe ratio (SR). Staunch systems traders should assume a maximum pre-cost SR of 0.40 and others an SR of 0.25. This implies that staunch systems traders should not pay more than 0.13 Sharpe ratio per year in costs, and semi-automatic traders and asset allocators no more than 0.08 SR. |
| Which instruments to trade | For a given type of trader there is a minimum level of turnover in round trips per year. Given a limit on how much you are prepared to pay in costs a year, and this minimum level of turnover, you will get a maximum feasible standardised cost. This implies that certain instruments will be too expensive to trade. Asset allocators can get down to an annual turnover of 0.40, so using my recommended maximum of spending 0.08 Sharpe ratio (SR) units on costs would exclude all instruments with costs greater than 0.20 SR. For semi-automatic traders, who I also suggest shouldn't pay more than 0.08 SR on costs, the lowest achievable turnover with a very loose stop loss is 1.8 round trips per year, so instruments with standardised costs greater than 0.044 SR can't be used. For staunch systems traders using my suggested set of trading rules the minimum turnover would be 12.5 round trips per year, which with my recommended limit of 0.13 SR a year on costs, implies that you shouldn't use instruments with costs greater than 0.01 SR. |
| Deciding average holding period | If you're a semi-automatic trader then I recommend that you should set your stop loss rule to give an average holding period so that turnover multiplied by standardised cost of your most expensive instrument is at most 0.08 Sharpe ratio units a year. |
| Selecting trading rules | You should exclude trading rules which are |

Too much capital

| When simple cost calculations aren't enough | If you can't always trade for half the spread, due to trades larger than the typical size at the top of the order book, then you need to use more complex cost models to account for execution costs. |

Too little capital

| Calculate maximum possible position | Staunch systems traders and semi-automatic traders should assume the maximum combined forecast of +20, which implies a maximum possible position of: 2 × volatility scalar × instrument weight × instrument diversification multiplier For asset allocating investors there is a constant forecast of +10, which implies a maximum possible position of: 1 × volatility scalar × instrument weight × instrument diversification multiplier |
| Very low rounded maximum possible position | I recommend taking action if the maximum possible position is less than four instrument blocks. Consider dropping the instrument, increasing the portfolio weight and/or reducing the number of instruments traded overall. |
| Sufficiently high rounded maximum possible position | No action required. I would personally be happy if the maximum possible position was at least four instrument blocks. |

Determining portfolio size and make-up

| Asset allocating investors and Staunch Systems Traders | You should hold the most diversified portfolio possible, consistent with avoiding issues with maximum positions that are too small. I recommend having a maximum possible position of at least four instrument blocks in any instrument. |
| Semi-automatic traders | Portfolio size is determined by the maximum number of bets. Check you won't have an issue with low maximum positions with any instrument before trading. |

This is the end of part three. Part four will delve further into
customising the framework as we look at three examples in detail:
the semi-automatic trader, the asset allocating investor and the
staunch systems trader.

---
122. 10 cents raw profit, less 1 cent to buy in and 1 cent to sell out.
123. Annual returns are the expected annualised standard deviation of percentage
returns (percentage volatility target) multiplied by Sharpe ratio. For pre-cost
returns 20% × 1.5 = 30%. For after cost returns 20% × 0.5 = 10%. Hence you must be
paying 30% - 10% = 20% in costs.
124. There may also be interest payments, gains or losses on FX translation, data
feeds, account management fees, various business costs for professionals, and if
you do well capital gains or income taxes. All these costs should be taken into
account when determining a trading system's likely net profitability.
125. This is the usual 'square root of time' factor of 16, assuming a 256 business
day year.
126. Staunch systems traders will use futures in the example in part four.
127. These are the conservative costs assuming you pay half the spread each time.
In practice I paid a fraction of this by using simple automated execution
algorithms. Nevertheless, I still use the more conservative costs when back-testing.
128. This is what semi-automatic traders will use in the example in part four.
129. Spread bets generally have higher trading costs than futures, and are OTC
traded rather than on exchange. On the upside as well as smaller block sizes they
offer tax free returns under current UK legislation.
130. For more discussion on this refer back to chapter two, page 52.
131. Again refer back to chapter two, page 52.
132. As you'll see later in the chapter on page 205, this requires using a very slow
look-back of 20 weeks for volatility estimation.
133. This figure is calculated when we cover the staunch systems trader example
in chapter fifteen on page 263.
134. As I showed you earlier, trading rules aren't the only source of turnover; we
also have changes in price volatility, which we'll discuss later in the chapter. The
costs you actually pay will also be inflated by the effect of the forecast
diversification multiplier. But for faster rules these are more than compensated by
the effect of position inertia: not trading position changes of less than 10%. All this
makes it very hard in practice to estimate the expected costs of trading a particular
rule. Looking solely at the turnover of the forecast is the simplest approach and is
usually conservative enough.
135. The set of rules in my own system have turnovers of between 65 and six times
a year, i.e. holding periods of between four business days and a couple of months.
As rules get slower than a turnover of six their performance does start to worsen,
and I exclude these rules entirely. For a turnover between six and 65, pre-cost
performance is relatively similar across variations of the same trading rules (and
is often worse for quicker trend following rules as most markets do not trend well
at shorter horizons). However some kinds of rules show better performance at
shorter holding periods and you should do your own bootstrapping with realistic
costs to check this.
136. The number of contracts to hold would be -0.524 and -1.049 respectively. Both
round to -1.
137. Doubling price volatility, all other things being equal, halves position size. The
number of contracts to hold would be -1.049 and -0.524 respectively. Both round to
-1.
138. Actually what you're trading here is the E-mini S&P 500 contract. There is an
even larger full size future.
139. Another option which is theoretically possible but isn't shown is to trade with
a higher volatility target by increasing the trading capital or the percentage
volatility target. The former isn't usually viable and the latter is almost always
extremely dangerous.