# Chapter Six. Instruments

BEFORE YOU THINK ABOUT *HOW* YOU TRADE YOU NEED TO consider *what* you are going to trade — the actual instruments to buy or sell. It's likely you will know which asset classes you want to deal with, based on your knowledge and familiarity with different markets.
However there are certain instruments that should be completely avoided for systematic trading. Others have characteristics which make them worse than other alternatives, or would force you to trade them in a particular way. Finally there is often a choice of how you can access a particular market; you could get Euro Stoxx 50 European equity index exposure by buying the individual shares, trading a future, a spread bet, a contract for difference, a passive index fund or an active fund. Which is best?

## Chapter overview

| Necessities | The minimum requirements that need to be met before you can trade an instrument. |
| :--- | :--- |
| Instrument choice and trading style | Characteristics that influence instrument choice between alternatives and how to trade particular instruments. |
| Access | Different ways to get exposure to instruments, and the benefits and downside of each. |

## Necessities
There are a few points to consider when deciding whether an instrument is suitable for systematic trading.

### Data availability
I'd like to be able to trade UK Gilt futures, but I don't have the right data licence so I can't get quoted prices. You can't trade systematically without access to prices and other relevant data.
At a minimum you will need accurate daily price information. Fully automated strategies that trade quickly or incorporate execution algorithms will need live tick prices. Fundamental trading strategies require yet more kinds of data. The costs of acquiring data on certain instruments, like Gilts perhaps, may be uneconomic for amateur investors.

### Minimum sizes
Another future I would like to trade — but can't — is the Japanese government bond (JGB) future. The contract currently sells for around 150 million yen, which is well over a million dollars. If I put this into my portfolio the maximum position I would want is 0.1 of a contract, which obviously isn't possible. Few amateur investors will be able to trade these behemoths.
In stocks the minimum size is one share, normally costing less than $1,000, although the A class of Berkshire Hathaway shares currently sell for over $100,000. Even for cheaper stocks, it may not be economic to trade in lots of less than 100 shares.
Minimum sizes reduce the granularity of what you can trade. Your positions become binary — all or nothing (in the case of JGBs, always nothing). This is an important subject and I will return to it in chapter twelve, 'Speed and Size'. As you'll see in that chapter this problem also affects the number of instruments you can hold in your portfolio.

### Why do prices move?
Do you know why bonds, equities and other instruments go up, or down, in price? "More buyers than sellers" is not an acceptable answer! I personally think it's important to have an understanding of what makes a market function; whether it be interest rates, economic news or corporate profits. This is vital if you're going to design ideas first trading rules.
It's also important to understand market dynamics once your system is running, if you want to avoid unpleasant surprises in markets that have become dysfunctional. As I'm redrafting this chapter, the Swiss government has just removed the peg which had held since 2011 fixing their currency at 1.20 to the euro, resulting in a massive Swiss franc (CHF) appreciation against all currencies. Thousands of traders including large hedge funds and banks were on the losing side, including many who were trading systematically. Fortunately I wasn't trading the EUR/CHF or USD/CHF FX pairs. For me there didn't seem any point in trying to make systematic forecasts, since I knew the market was controlled by central bank intervention rather than the normal historic factors driving prices in the back-test. Keeping abreast of markets will help you to avoid similarly dangerous instruments.

### Standard deviation
There is another reason why I excluded Swiss FX positions from my systematic trading strategies, which was the extremely low volatility of prices whilst the peg was in place. In principle my framework can deal equally well both with assets whose returns naturally have low standard deviations and those that are very risky. It can also cope with changes in volatility over time.
However instruments which have extremely low risk like pegged currencies should be excluded. Firstly, when risk returns to normal it is liable to do so very sharply, potentially creating significant losses. Secondly, these positions need more leverage to achieve a given amount of risk, magnifying the danger when they do inevitably blow up. Even if you don't use leverage they will limit the risk your overall trading system can achieve.<sup>74</sup> Finally, they also tend to be more costly to trade, as you will discover in chapter twelve, 'Speed and Size'.

## Instrument choice and trading style
With your pool of available instruments narrowed by excluding those which don't have the necessary attributes mentioned above, you need to decide which of those remaining you prefer to trade. These characteristics will also influence *how* you'll trade the instruments you've chosen.

### How many instruments?
I like my portfolio of instruments to be as large and diversified as possible, as long as I don't run into issues with minimum sizes, for example as I would do with Japanese government bonds. The maximum number of instruments you can have will depend on minimum sizes, the value of your account and how much risk you're targeting (which you'll learn about in chapter nine, 'Volatility targeting').
In chapter twelve, 'Speed and Size', you'll see how to calculate the point at which you could run into problems with minimum instrument size. You will then be able to work out what size of portfolio makes sense.
Then in part four I will give some recommended portfolios in each example chapter, which have been constructed to be as diversified as possible given the level of the volatility target and the available instruments.

### Correlation
If you already owned shares in RBS and Barclays then the last thing you would want to add to your portfolio is another UK bank like Lloyd's. Generally you should want to own or trade the most diversified portfolio possible, where the average correlation between the assets is lower than the alternatives. If there are a limited number of instruments that you can fit in your portfolio then it makes sense to pick those with lower correlations.

### Costs
Given the choice between two otherwise identical instruments you should choose the cheapest to trade. So, if you can, use a cheap FTSE 100 future rather than an expensive spread bet to get exposure to the UK equity index.<sup>75</sup> Instruments that are expensive to trade are clearly less suitable for dynamic strategies, particularly those that involve faster trading.
Sometimes you have to trade an expensive instrument, if it's the only way of accessing a particular asset. In this case you should trade it more slowly. There is however a maximum acceptable cost depending on the type of trading that you're doing, so some instruments will be completely unsuitable. Because the cost of trading is so important it will be covered in great detail in chapter twelve, 'Speed and Size'.

### Liquidity
Closely related to costs is liquidity. Less liquid instruments are likely to be more expensive to trade quickly or in larger amounts. This is more of a problem for large institutional investors and those trading fast. Liquidity is not constant and can reduce quickly in times of severe market stress, particularly for non exchange traded 'over the counter' instruments, as in the Credit Default Swap derivatives markets in 2008.
Again chapter twelve, 'Speed and Size', will explain how those with larger account sizes will need to understand costs and liquidity better than small investors.

### Skew
Should you avoid negative skew in your portfolio from instruments like holding short VIX (US equity volatility index) futures? Remember I covered the skew of assets and trading rules in chapter two, 'Systematic Trading Rules'. Static strategies will inherit the skew of their underlying instruments, but the skew of a dynamic strategy also depends on the style of your trading rule. So using a positive skew rule like trend following on a negative skew asset will alleviate some of the danger.
As you will see in chapter nine, 'Volatility targeting', you need to be extremely careful if the overall returns of your trading system are expected to have negative skew. Instruments with extreme negative skew will often have very low standard deviation for most of the time, and should be excluded on those grounds.

## Access
Finally you need to choose the route by which you access the underlying assets you're going to trade.

### Exchange or OTC
Does your instrument trade on an exchange like shares in General Electric and Corn futures, or over the counter (OTC) like foreign exchange (FX)? There are often different ways of trading the same underlying asset, some via exchange, others OTC. So a spread bet on the CHF/USD FX rate is OTC, whilst the Chicago future on the same rate is exchange traded.
If you have a choice then, all other things being equal, should you trade on exchange or OTC? In the January 2015 Swiss franc meltdown traders using OTC brokers suffered a variety of difficulties, including dealers not accepting orders or displaying quotes, trades not being honoured and fills re-marked after the fact, and in extreme cases potential account losses as brokers went into liquidation.
Those who traded the CHF/USD future had difficulty finding deep liquidity, but otherwise the market operated as normal. In conclusion it's normally better to trade on exchange if you can.

### Cash or derivative
'Cash' is simply where you own the underlying asset directly — perhaps a share in British Gas or a bond issued by General Electric. Alternatively you can own a derivative on an asset, like a future, Contract for Difference or spread bet.<sup>76</sup> The main advantage of derivatives is that they offer straightforward leverage. Without leverage it might be difficult to reach your volatility target, which will reduce the returns you can earn. There may also be different tax treatments; in the UK for example spread bets are treated as gambling, which means winnings are tax free but losses aren't deductible.
Various types of derivatives may have different trading costs, and also have different minimum sizes, liquidity and market access. For example a FTSE 100 future is cheaper to trade and more liquid than the corresponding spread bet. It also has the advantage of being accessed via an exchange, whereas the spread bet is OTC. But the future has a larger minimum size which precludes its use by smaller investors.

### Funds
Other options for trading the FTSE 100 are to buy an index tracker like an exchange traded fund (ETF). These are collective funds — instruments which buy you a share in a portfolio of assets. As well as ETFs, collective funds include US mutual funds, UK unit trusts and investment trusts. Normally for systematic trading you will be interested in passive funds like index trackers. These contain baskets of assets weighted to match an index like the FTSE 100 or S&P 500.
Passive funds normally have relatively low annual fees and minimum sizes, but frequently cost more than the relevant derivative to trade. But they can be useful instruments when leverage can't be used, or when a market can't be accessed another way.
In some cases you might want to use active funds, where the weights to different assets are determined by the fund manager. This might make sense if there is no relevant passive fund or derivative, but fees are higher on active funds, and the presence of any compensating manager skill or alpha is very hard to prove. Collective funds can have quirks such as daily remarking, tax treatment, internal leverage and discounts to net asset value which you should fully understand before using them.

## Summary of instrument choice

| Data availability | At a minimum you need daily price data to trade an instrument systematically. For fundamental strategies you also need other relevant data, e.g. price:earnings if you're using an equity value rule. |
| :--- | :--- |
| Minimum sizes | For small investors large minimum trading sizes can be a problem. |
| Understand what moves returns | Don't trade from an ivory tower; have some idea of the factors driving returns. If unusual forces are at play then avoid that instrument. |
| Standard deviation of returns | Volatility must not be extremely low. |
| How many instruments? | Given the size of your account and the minimum size of each instrument you can determine whether you will run into problems given a particular sized portfolio. You should then hold the largest portfolio you can given those constraints. |
| Correlation of returns | You should always try and have a portfolio where assets are as diversified as possible. |
| Costs | Cheaper is better. Expensive instruments will need to be traded more slowly, and may be too pricey to trade at all. |
| Liquidity | For larger and less patient investors liquidity is vital. |
| Skew of returns | Assets with strong negative skew need careful handling and shouldn't dominate your portfolio. Using the right trading rules can improve skew to some degree. |
| Trading venue | Is the market accessed via exchange, or over the counter (OTC)? On exchange is preferable. |
| Cash or derivative | Should you trade the asset outright, or a derivative based on its value, and if so which one? |
| Collective funds | Investment through collective funds can make sense when derivatives can't be used. |

Now you know *what* you are going to trade, the next step is to think about *how*. So the next chapter will cover the business of forecasting prices.

---
74. I'll return to this topic in chapter nine, 'Volatility targeting'.
75. I'll explain why the spread bet is more expensive in chapter twelve, 'Speed and Size'.
76. I've deliberately excluded options and other non-linear derivatives from this list, since these can't be used casually as substitutes for the underlying assets.
