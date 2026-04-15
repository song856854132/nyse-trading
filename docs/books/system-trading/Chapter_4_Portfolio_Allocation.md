Chapter Four. Portfolio Allocation

Staunch systems trader
Asset allocating investor

This chapter is about deciding how you share out your trading capital between different instruments or trading rules. Deciding the allocation between instruments is important for asset allocating investors, whilst staunch systems traders have to make both kinds of decision.
It isn't relevant if you're a semi-automatic trader, since you won't use systematic trading rules and will trade different instruments opportunistically. You can skip this chapter.

DECIDING HOW TO ALLOCATE WITHIN A PORTFOLIO OF assets is a problem every investor faces. How much in equities, bonds or cash? Should you split your equity allocation evenly between countries or just stick it all in the USA?
Allocation decisions are equally important for systematic investors and traders. If you're a staunch systems trader running more than one trading rule, including any variations, then you need to decide what forecast weights to use when you combine rules together to forecast the price of each instrument.
Both staunch systems traders and asset allocating investors also need to decide instrument weights; how much of your portfolio to put into the trading systems you have for each instrument. Because the tools in this chapter are for making both kinds of decision, I'll refer to portfolios of generic assets, which could be either instruments or trading rules. Later in the book I'll show you specific examples of each of the two types of allocation problem.
Just like trading rules, portfolio weights can be over-fitted.
Optimising weights can give you a portfolio which does really well in back-tests, but which fails badly when traded in reality. Such portfolios are usually highly extreme; allocating to just a small subset of the assets available. In this chapter I'll show you how to avoid the pitfalls of these highly undiversified portfolios.

Chapter overview

| | |
| --- | --- |
| Optimising gone bad | How classic portfolio optimisation can often result in over-fitted extreme portfolio weights. |
| Saving optimisation from itself | Some insights from an alternative technique, bootstrapping, which can help us understand what is going wrong. |
| Making weights by hand | How to use a simple method called handcrafting to get portfolio weights. |
| Incorporating Sharpe ratios | Using additional information about expected performance to improve handcrafted weights. |

Optimising gone bad
Introducing optimisation
Portfolio optimisation will find the set of asset weights which give the best expected risk adjusted returns, usually measured by Sharpe ratio. The inputs to this are the expected average returns, standard deviation of returns, and their correlation. The standard method for doing this was first introduced by Harry Markowitz in the 1950s. It was a neat and elegant solution to a complex problem.
Unfortunately it's all too easy to be distracted by elegance, and forget the important assumptions underlying the maths. As you will see below, blind use of this method frequently results in ugly portfolios with extreme weights. Just because an equation is wonderful to behold doesn't mean you should slavishly use its results without thought of the consequences. As Einstein said, "If you are out to describe the truth, leave elegance to the tailor."
In the early part of my career I was fatally distracted by the lovely equations and ended up with some terrible portfolios, until I learned the error of my ways. Subsequently I often had to review the allocation decisions made by researchers who were less experienced, although undoubtedly cleverer and more academically qualified than myself.
When I asked one of these rocket scientists what they thought about the extreme portfolio weights they'd found I often got a shrug. "These are what the optimiser came up with." The unspoken assumption was that the equation must be right. Hopefully after reading this chapter you will be less accepting of attractive mathematics.

Some good news
Portfolio optimisation is hard. But there are a few difficulties that don't arise when you're using it to design trading strategies. This is because you aren't deciding directly how large your positions in various instruments should be. Instead you're deciding what weight should be given to different parts of your trading system. These can either be the forecast weights telling you in what proportion to use trading rule variations for a particular instrument, or the instrument weights determining how much of your capital to allocate for trading each instrument.
This gives you two advantages. Firstly, you can't have negative weights in your portfolio; you can't short trading rules, so the lowest possible weight is zero. If a trading rule is expected to lose money you shouldn't include it at all.56 Secondly, using my framework will mean that profits from your trading rules have identical expected standard deviation of returns. This is because of the volatility standardisation I spoke about in chapter two, 'Systematic Trading Rules'. By using this technique you simplify the problem and only need to use expected Sharpe ratios and correlations to work out your weights.
Although you won't be optimising the underlying positions in individual assets like equities or bonds in your trading systems, I will be using portfolios of simple assets in this chapter to make the examples more straightforward. However to make it easier to interpret the results I will adjust asset returns before any calculations so that they have the same standard deviation as you'll have when you work with trading system returns.

The unstable world of portfolio weights
Let's take a simple example of allocating capital between three assets: the NASDAQ and S&P 500 US stock indices, and the US 20 year benchmark bond. I am using data from January 1999 to mid-2014 and all returns are volatility standardised to have the same expected standard deviation. Each year from January 2000 onwards I'm going to use returns from all previous years to calculate some optimal weights.57 Because each optimisation uses all available data to create a single set of weights I call this a single period optimisation.
The calculation is done using the classic Markowitz optimisation; I find the maximum risk adjusted return (e.g. Sharpe ratio) using the estimated means and correlations, and standard deviations (which are all identical because I've used volatility standardisation). I also don't allow weights to be negative and they have to sum up to exactly 100%.
Figure 14 shows the weights calculated for each year.58 In the last throes of the late 1990s tech boom I naturally put all my money into the fast rising NASDAQ. This then implodes, and is permanently removed from the portfolio. For much of the remaining period I put my entire capital in bonds. At the end I only have 25% in equities, all of which is in the S&P 500. This is a very extreme portfolio, with very unstable weights.

FIGURE 14: SINGLE PERIOD OPTIMISATION USUALLY MEANS EXTREME WEIGHTS
The figure shows the portfolio weights produced by single period optimisation done each year on all previous data.

Not all statistical estimates are created equal
Faced with such nightmares a natural reaction is to discard any hope of optimising. Perhaps we should just allocate equally to all the assets we have. Many academic researchers have also come to this conclusion and there is plenty of evidence that equal weights are hard to beat.59
When do equal weights make sense?60
1. Same volatility: If all assets had the same expected standard deviation of returns. This is always the case for the volatility standardised assets we're using.
2. Same Sharpe ratio: If all assets had the same expected Sharpe ratio (SR).
3. Same correlation: If all assets had the same expected co-movement of returns.

If these assumptions aren't correct, then what should your portfolio look like?61
What kind of portfolio should we have with...
1. Same Sharpe ratio and correlation: Equal weights.
2. Significantly different Sharpe ratio (SR): Larger weights for assets that are expected to have higher SR, smaller for low SR.
3. Significantly different correlation: Larger weights for highly diversifying assets which have lower correlations to other assets, and smaller for less diversifying assets.

Let's see if these assumptions are true in the simple example. Figure 15 shows the distribution of Sharpe ratios for each of the three assets. Notice that the lines mostly overlap; this means we can't distinguish between the historic performance of each asset. Although bonds did have a higher average SR the advantage isn't statistically significant. If you read the previous chapter, and remember table 6, it is no surprise that the 15 years of data isn't enough to say with confidence which asset had the best SR.

FIGURE 15: HARDER TO DISTINGUISH SHARPE RATIOS THAN YOU THINK
The figure shows the distribution of Sharpe ratios for the three assets in my example portfolio.

On the contrary, we can often distinguish different correlations. Figure 16 shows the distribution of correlations in my simple example. You should be able to easily pick apart the correlated equities and the diversifying bond asset.
So in the simple example I should be able to do better than equal weights, as there is significant data about correlations. A good portfolio would have more of the diversifying bond asset than the equities, but wouldn't take much account of the insignificantly different Sharpe ratios. However the classic optimiser doesn't work like this, because it can't see all the information in figures 15 and 16. It uses only the average SR and correlation, not knowing or caring how much uncertainty there is in each estimate.

FIGURE 16: EQUITIES CLEARLY CORRELATED WITH EACH OTHER, AND NEGATIVELY WITH BONDS
The figure shows the distribution of correlations for pairs of the three assets in my example portfolio.

Saving optimisation from itself
How can we fix this problem? I have two techniques that I use. The first, which is quite hard work, is called bootstrapping. This involves repeating my optimisation many times over different parts of the data, taking the resulting weights, and averaging them out. So the weights are the average of many optimisations, rather than one optimisation on the average of all data.
The justification for bootstrapping is simple. I believe that the past is a good guide to the future, but I don't know which part of the past will be repeated. To hedge my bets I assume there is an equal chance of seeing any particular historical period repeated. So it's logical to use an average of all the portfolios which did best in previous periods.
Bootstrapping has some nice advantages over classic optimisation. Most of the individual optimisations have extreme weights. However with enough of them it's unlikely the average will be extreme. If I have noisy data, and the past contains periods which were very different, then the optimal portfolios will be close to equal weights. But with significant differences in Sharpe ratios or correlations similar portfolios will crop up repeatedly, and the average will reflect that. The averaged weights naturally reflect the amount of uncertainty that the data has.
Let's see the results of running an expanding window bootstrap optimisation on our simple three asset portfolio. Figure 17 shows the results over time, whilst table 7 compares the final weights with a classic single period optimisation and equal weights.62 After the first year the weights are relatively stable, and for all periods less extreme than for the single period method. However the diversifying allocation to bonds is greater than with equal weights, so this portfolio should do better.

FIGURE 17: BOOTSTRAPPED PORTFOLIO WEIGHTS: STABLE AND EVENLY SPREAD
The figure shows the portfolio weights I get over time from using the bootstrap method on the example assets.

TABLE 7: BOOTSTRAPPED WEIGHTS ARE MORE EVEN THAN THE SINGLE PERIOD METHOD, BUT ACCOUNT FOR CORRELATIONS BETTER THAN EQUAL WEIGHTS

| | Equal weight | Single period | Bootstrapped |
| --- | --- | --- | --- |
| US 20 year bond | 33% | 68% | 53% |
| S&P 500 equities | 33% | 32% | 27% |
| NASDAQ equities | 33% | 0% | 20% |

The table shows the final portfolio weights using equal weights and after optimising using both single period and bootstrapped methods with an expanding window.

Bootstrapping requires a suitable software package, the ability to write your own optimisation code, or a black belt in spread-sheeting. If you are interested in this technique there are more details in appendix C. Meanwhile I'm going to show you the second, much simpler, way I use to get robust portfolio weights.

Making weights by hand
Something weird happens if you ask an experienced and skilled expert in portfolio optimisation, but not one who uses bootstrapping, to do some work for you. Under your gaze they will pull out their optimisation software and diligently produce some weights. As we've seen these are inevitably awful, with many assets having zero weights and one or two having huge allocations. The artisan will then suggest you go for a coffee whilst they do their magic.
When you return the weights have suspiciously changed; they're now much nicer and less extreme. Upon interrogation the expert will admit they have tortured the software with all kinds of arcane tricks until it produced the right result. Experts know from glancing at the problem roughly what a good answer should look like, and their skill lies in extracting it from the computer.
I remember once being told "Optimisation is more of an art than a science." This never seemed particularly satisfying. I would have preferred a process that always produced exactly the same result for the same data set, regardless of who was operating the machinery.
After leaving the financial industry I set myself the task of creating my own trading system, which naturally meant doing some optimisation. As it would take time to write the necessary code for bootstrapping I thought I'd use the simpler single period method for my first attempt. I soon found myself with weights I didn't like, and true to form began fiddling to improve them. After toying with the optimiser for a few minutes, I quickly realised it would be better to cut out the artistic pseudo-optimisation stage entirely. Why not just write down the right weights to start with?
The only tool required would be a sharp pencil, and something like the back of an envelope or a beer mat to write on. A little harder was defining exactly what 'good' weights would look like for a given portfolio.
I started with small portfolios. For simple situations where equal weights were justified this was easy. To deal with more difficult groups I used the results from experiments on artificial data with the bootstrapping method.
To cope with larger portfolios I made the problem modular. So I first worked on subsets of the portfolio which I formed into groups, and then calculated the weight of each group relative to others. If necessary I used more than one level of grouping depending on how complicated the problem was.
The handcrafting method was born. Let's see how it works in more detail.

Handcrafting method
The procedure involves constructing the portfolio in a bottom-up fashion by first forming groups of similar assets. Within and across groups you set allocations using a table of optimal weights for similar portfolios. These weights come from my own experiments with bootstrapping.
As you would expect the method assumes that all assets have the same expected standard deviation of returns. I also assume, for now, that they also have the same Sharpe ratio (SR). I'll relax that assumption later, but as you saw above and perhaps in the last chapter it's quite common to be unable to find statistically significant differences between the Sharpe ratios of assets.
So all you need is an idea of what correlations are likely to be. As you'll see these don't need to be precise, and you can either estimate them with historical data or take an educated guess given the nature of the assets in your portfolio. If you don't want to do your own guessing then tables 50 to 57 in appendix C show some rough correlations between the returns of different instruments, and sets of different trading rules for the same instrument.
Once you have your correlations you need to group the most highly correlated assets together. Except with unusual portfolios the groupings will normally be pretty obvious; so for example in a Nikkei stock portfolio you'd probably put all Japanese utility stocks together, all banks together and so on.
Groups should ideally contain only one, two or three assets, but more is okay if their correlations are similar enough. Within these small groups there are only a limited number of distinctive correlation patterns that really matter.
The correct weights for these patterns are shown in table 8. If the exact correlation value isn't shown then you should round to the closest relevant number.63 Negative values should be floored at zero.64 The three asset correlations shown are those between assets A and B, A and C, and B and C respectively. These give the weights shown for assets A, B and C respectively.

TABLE 8: GROUP WEIGHTS TO USE WHEN HANDCRAFTING PORTFOLIOS

| | | |
| --- | --- | --- |
| Group of one asset | 1 | 100% to that asset |
| Any group of two assets | 2 | 50% to each asset |
| Any size group with identical correlations | 3 | Equal weights |
| Four or more assets without identical correlations | 4 | Split groups further or differently until they match another row |
| Three assets with correlations AB, AC, BC | | Weights for A, B, C |
| 3 assets correlation 0.0, 0.5, 0.0 | 5 | Weights: 30%, 40%, 30% |
| 3 assets correlation 0.0, 0.9, 0.0 | 6 | Weights: 27%, 46%, 27% |
| 3 assets correlation 0.5, 0.0, 0.5 | 7 | Weights: 37%, 26%, 37% |
| 3 assets correlation 0.0, 0.5, 0.9 | 8 | Weights: 45%, 45%, 10% |
| 3 assets correlation 0.9, 0.0, 0.9 | 9 | Weights: 39%, 22%, 39% |
| 3 assets correlation 0.5, 0.9, 0.5 | 10 | Weights: 29%, 42%, 29% |
| 3 assets correlation 0.9, 0.5, 0.9 | 11 | Weights: 42%, 16%, 42% |

Numbers in bold in middle of table are used to identify rows.

Note that there are other permutations of these correlations which aren't shown here that would just be a re-ordering of a set of values included in the table. So for example suppose your portfolio has three assets: US bonds (D), S&P 500 (E) and NASDAQ (F); with correlations of -0.3 (DE), -0.2 (DF) and 0.8 (EF); which you would round to 0.0 (DE), 0.0 (DF), 0.9 (EF).
After reordering and mapping to ABC in the table the relevant row number 6 is 0.0 (DE mapping to AB), 0.9 (EF mapping to AC), 0.0 (DF mapping to BC) giving weights of 27% (A), 46% (B), 27% (C). Expressing that back in the original problem (E=A, D=B, F=C) the weights are US Bonds 46% (D), S&P 500 27% (E) and NASDAQ 27% (F).65
Let's think about the intuition of where these weights come from. Equities aren't very diversifying since they have a correlation of 0.90 with each other. But bonds are uncorrelated with the two equity indices, so add more diversification to the portfolio. So it makes sense that they get a higher weight, and the weight of the equities sinks lower.
Once every group has been processed you then allocate weights to groups, based on your guess or estimate of the correlation between groups.66 Finally the weight of each asset in the overall portfolio is just the total weight of its group multiplied by the weight it has within the group.
Depending on the size and structure of the portfolio this process could be done with two levels as explained here, at just one level if all the assets fall readily into table 8 without needing subgroups, or with three or more levels.
To see how grouping works consider again the three asset portfolio of US bonds, S&P 500 and NASDAQ. Common sense and the correlations estimated above imply I should create one group for the single bond asset, and a second group for the two equity indices. Here is how I calculated the weights. The row numbers shown refer to the relevant rows of table 8.

| | |
| --- | --- |
| First level grouping<br>Within asset classes | Group one (bonds): One asset, gets 100%. Row 1.<br>Group two (equities): Two assets, I place 50% in each. Row 2. |
| Second level grouping<br>Across asset classes | I have two groups to allocate to, each gets 50%. Row 2. |

Each equity index gets 50% (within group weight) multiplied by 50% (weight of group) which is 25%. The one bond asset gets the other 50%. The weights are shown in figure 9. They are fairly close to the ungrouped handcrafted weights, and to what the full bootstrap method gave us in its final iteration - despite both handcrafting methods taking only a few seconds and needing no computing power. Because I didn't use Sharpe ratios there isn't the slight overweight on bonds and S&P 500 that we have in the bootstrapped results. I'll address that shortcoming below.

TABLE 9: HANDCRAFTED WEIGHTS ARE SIMILAR TO BOOTSTRAPPED WEIGHTS, BUT WITH LESS WORK

| | Equal weight | Single period | Bootstrapped | Handcrafted ungrouped | Handcrafted grouped |
| --- | --- | --- | --- | --- | --- |
| US 20 year bond | 33% | 68% | 53% | 46% | 50% |
| S&P 500 equities | 33% | 32% | 27% | 27% | 25% |
| NASDAQ equities | 33% | 0% | 20% | 27% | 25% |

The table shows the final portfolio weights using equal weights, after optimising using both single period and bootstrapped methods with expanding windows, and using handcrafting without and with grouping.

A more complex example
Now for a harder challenge. Suppose I have a portfolio of three UK banks (Barclays, HSBC and RBS), two UK retailers (Tesco and Sainsburys), three US banks (JP Morgan, Citigroup and Bank of America), three US retailers (Safeway, Walmart and Costco), two UK government bonds (5 year and 10 year) and three US bonds (2 year, 20 year and 30 year). I grouped these, from the lowest grouping upwards as follows: equity sector, country and asset class, giving the grouping in table 10.

TABLE 10: GROUPING FOR LARGER EXAMPLE PORTFOLIO

| | 1st level | 2nd level | 3rd level | 4th level |
| --- | --- | --- | --- | --- |
| Barclays | UK banks | UK equities | Equities | Whole portfolio |
| HSBC | | | | |
| RBS | | | | |
| Tesco | UK retailers | | | |
| Sainsbury | | | | |
| JP Morgan | US banks | US equities | | |
| Citigroup | | | | |
| Bank of America | | | | |
| Safeway | US retailers | | | |
| Walmart | | | | |
| Costco | | | | |
| 10 year UK bond | UK bonds | | Bonds | |
| 20 year UK bond | | | | |
| 2 year US bond | US bonds | | | |
| 20 year US bond | | | | |
| 30 year US bond | | | | |

Here is how I calculated the weights. Relevant rows of table 8 are shown.

| | |
| --- | --- |
| First level grouping<br>By equity industry within country, by bond country | Within equities I'm going to assume stocks have similar correlations if they're within the same industry and country.<br>• UK banks: Assuming similar correlations allocate 33.3% to each. Row 3.<br>• UK retail: Two assets so allocate 50% to each. Row 2.<br>• US banks: Similar correlations so allocate 33.3%. Row 3.<br>• US retail: Similar correlations so allocate 33.3%. Row 3.<br>• UK bonds: Two assets so allocate 50% to each. Row 2.<br>• US bonds: For the three US bonds things are a little more complex. From table 55 (page 308) the 2 year and 20 year bonds typically have 0.5 correlation, 2 year/30 year 0.5 and 20 year/30 year 0.9. This matches row 10 of table 8, giving weights of 42% in the 2 year bond and 29% in each of the 20 and 30 year bonds. |
| Second level grouping<br>By country within asset class | • UK equities: Two groups (UK banks and UK retailers) so allocate 50% to each. Row 2.<br>• US equities: Two groups (US banks and US retailers) so allocate 50% to each. Row 2.<br>• UK bonds: 100% as only one group. Row 1.<br>• US bonds: 100%, one group. Row 1. |
| Third level grouping<br>By asset class | Equities: Two groups (US equities and UK equities) so allocate 50% to each. Row 2.<br>Bonds: Two groups (US and UK bonds) so allocate 50% to each. Row 2. |
| Fourth level grouping<br>Across asset classes | Two grouped assets (bonds and equities) allocate 50% to each. Row 2. |

Final weights
The final weights for each asset, from multiplying the weights they are given at each grouping stage, are shown in table 11.
Notice I mostly didn't use correlations except in the US bonds group. If you can keep your groups down to one or two members, or your group members are similarly correlated, then you don't need to use correlations once you've determined your groups.
With 16 assets equal weights would have come out at 6.25% each. This was an unbalanced portfolio with more equities than bonds, and where it was unrealistic to assume identical correlations. In this situation we should be able to beat equal weights by giving more allocation to more diversifying assets.

TABLE 11: CONSTRUCTION OF WEIGHTS IN LARGER EXAMPLE PORTFOLIO

| | 1st | 2nd | 3rd | 4th | Final |
| --- | --- | --- | --- | --- | --- |
| Barclays | 33% | 50% | 50% | 50% | 4.2% |
| HSBC | 33% | 50% | 50% | 50% | 4.2% |
| RBS | 33% | 50% | 50% | 50% | 4.2% |
| Tesco | 50% | 50% | 50% | 50% | 6.3% |
| Sainsbury | 50% | 50% | 50% | 50% | 6.3% |
| JP Morgan | 33% | 50% | 50% | 50% | 4.2% |
| Citigroup | 33% | 50% | 50% | 50% | 4.2% |
| Bank of America | 33% | 50% | 50% | 50% | 4.2% |
| Safeway | 33% | 50% | 50% | 50% | 4.2% |
| Walmart | 33% | 50% | 50% | 50% | 4.2% |
| Costco | 33% | 50% | 50% | 50% | 4.2% |
| 10 year UK bond | 50% | 100% | 50% | 50% | 12.5% |
| 20 year UK bond | 50% | 100% | 50% | 50% | 12.5% |
| 2 year US bond | 42% | 100% | 50% | 50% | 10.5% |
| 20 year US bond | 29% | 100% | 50% | 50% | 7.3% |
| 30 year US bond | 29% | 100% | 50% | 50% | 7.3% |

Calculation of weights is shown for each grouping stage, and in the last column we have the final portfolio weight, which is the product of the weights for each stage. Borders show grouping. There is some rounding.

Are we cheating?
The handcrafting method cannot easily be repeated automatically in multiple years, so is unsuitable for an expanding or rolling out of sample back-test.67 You fit one single in sample set of portfolio weights, with knowledge of all past data. Arguably there is a danger that the resulting portfolio will be over-fitted. This is more likely if you're using estimated correlations, although it's also an issue with correlations that are educated guesses, since both imply you knew the future at the start of the back-test.
Relax; you will be using information from the future but in mitigation the weights you'll produce will be much less extreme than an in sample single period optimisation will produce. Also correlations usually don't move enough that handcrafted weights would be dramatically different over time. So the weights you will produce using all data are likely to be very similar if you do them earlier in the back-test using only past data. Also for now the method ignores differences in Sharpe ratio (SR), which also ensures weights are not extreme and relatively stable.
To illustrate this I fitted the trading system I outline in chapter fifteen for staunch systems traders. Using in sample handcrafting rather than rolling out of sample bootstrapping gave an insignificant advantage (Sharpe ratio of 0.54 rather than 0.52). In comparison in sample single period optimisation produced an unrealistically high SR of 0.84; although when I used the single period method to perform a rolling out of sample fit it did much worse, with an SR of 0.3.
Nevertheless the results of back-testing handcrafted portfolios should be treated with slightly more scepticism than a true out of sample method like bootstrapping.

Incorporating Sharpe ratios
The basic handcrafting method assumes all assets have the same expected Sharpe ratio (SR). Usually you don't have enough data to determine whether historic SR were significantly different. However there might be times when you have a valid opinion about relative asset Sharpes.
One example which I'll return to later is when some assets have higher costs than others. Costs are known with much more certainty than raw performance, so you can usually have a statistically well informed opinion about their effect on returns.
Another scenario is where you are following my recommended procedure for trading rule selection outlined in the previous chapter. With my preferred method you don't remove unprofitable trading rules before deciding what their forecast weights should be. However if a rule is terrible in back-test you'll want to reduce its weight, although it will probably have some allocation, since it's hard to find sufficient evidence that one rule is definitely better or worse than another (as covered in the last chapter).
By experimenting with random data I calculated how bootstrapped portfolio weights change in a group of assets whose true SR are not equal. These adjustments can then be applied to handcrafted weights. These results are below in table 12. To avoid showing infinite permutations the results are in relative terms, so it's the SR relative to the average for the group that matters.

TABLE 12: HOW MUCH SHOULD YOU ADJUST HANDCRAFTED WEIGHTS BY IF YOU HAVE SOME INFORMATION ABOUT ASSET SHARPE RATIOS?

Adjustment factor
| SR difference to average | (A) With certainty e.g. costs | (B) Without certainty, more than ten years' data | (C) Without certainty, less than ten years' data |
| --- | --- | --- | --- |
| -0.50 | 0.32 | 0.65 | 1.0 |
| -0.40 | 0.42 | 0.75 | 1.0 |
| -0.30 | 0.55 | 0.83 | 1.0 |
| -0.25 | 0.60 | 0.85 | 1.0 |
| -0.20 | 0.66 | 0.88 | 1.0 |
| -0.15 | 0.77 | 0.92 | 1.0 |
| -0.10 | 0.85 | 0.95 | 1.0 |
| -0.05 | 0.94 | 0.98 | 1.0 |
| 0 | 1.00 | 1.00 | 1.0 |
| 0.05 | 1.11 | 1.03 | 1.0 |
| 0.10 | 1.19 | 1.06 | 1.0 |
| 0.15 | 1.30 | 1.09 | 1.0 |
| 0.20 | 1.37 | 1.13 | 1.0 |
| 0.25 | 1.48 | 1.15 | 1.0 |
| 0.30 | 1.56 | 1.17 | 1.0 |
| 0.40 | 1.72 | 1.25 | 1.0 |
| 0.50 | 1.83 | 1.35 | 1.0 |

The table shows the adjustment factor to use for handcrafted weights given the Sharpe ratio (SR) of an asset versus portfolio average (rows), certainty of SR estimate and amount of data used to estimate (columns). Column A: SR difference is known precisely, e.g. different trading costs. Column B: SR estimated using more than ten years of data or forecasted. Column C: SR estimated using less than ten years of data.

Initially my experiments assumed I knew the true SR difference. For cost adjustments this is a fair assumption. Column A shows the adjustment factor to multiply the starting portfolio weights by when we know differences with complete certainty.
However if you are using historical estimates of SR, or forecasting them in some other way, then you can't be as confident. You should use the less aggressive adjustment factors in column B. Finally if you're estimating SR based on less than ten years of data I advise not adjusting at all. As you might have seen in the last chapter estimates of SR are extremely unlikely to be statistically different after only a few years. Though it's trivial I've put this in column C of the table.

Follow these steps to adjust handcrafted weights for Sharpe ratio

| | |
| --- | --- |
| Starting weights | Work out the handcrafted weights for the group. These will add up to 100%. |
| Get Sharpe ratios | In each group using historical data, cost estimates, or some other method, find the expected SR for each asset. |
| Sharpe versus average | Calculate the average SR for the entire group and then work out the relative difference higher or lower than this for each asset. |
| Get multiplier | Find the weight multiplier for each asset from column A, B or C in table 12, depending on how certain you are about the SR estimate, and if relevant how much data was used. |
| Multiply | Multiply each of the weights in the group by the relevant multiplier. |
| Normalise | The resulting weights in the group may not add up to 100%. If necessary normalise the weights so they sum to exactly 100%. |

If you have two or more levels of grouping you'll need to repeat this process. When you move up to the next level you should estimate the SR of each group as a whole. You can do this by back-testing each group's returns, taking a weighted average of the SR for each individual asset in the group, or just using a simple average SR across the group's assets. The process for adjusting group weights is then the same as for within groups.

A simple example
Let's return to the simple three asset portfolio of two US equity and one bond market, using handcrafting with groups. My historic estimates of Sharpe ratios are around 0 for NASDAQ, 0.5 for S&P 500 and 0.75 for bonds. Here is what I did with the equity group (the bond group is still just 100% in a single asset):

| | |
| --- | --- |
| Starting weights | NASDAQ: 50%, S&P 500: 50% |
| Estimate Sharpes | NASDAQ: 0, S&P 500: 0.5 (from historical data) |
| Sharpe versus average | Average: 0.25. Difference to average:<br>• NASDAQ 0 - 0.25 = -0.25<br>• S&P 500 0.5 - 0.25 = 0.25 |
| Get multiplier | I have uncertain estimates with over ten years of data so I use column B of table 12:<br>• NASDAQ: 0.85<br>• S&P 500: 1.15 |
| Multiply | NASDAQ: 50% × 0.85 = 42%<br>S&P 500: 50% × 1.15 = 58% |
| Normalise | Total is 100% so no normalisation required. |

Now for the second level where I mix bonds and equities

| | |
| --- | --- |
| Starting weights | Equities: 50%, Bonds: 50% |
| Guess Sharpes | Equities: using a simple average of NASDAQ with SR of 0 and S&P 500 with SR 0.5, I get an average of 0.25<br>Bonds: 0.75 from historical data. |
| Sharpe versus average | Average across bonds and equities: 0.50. Difference to average:<br>• Equities 0.25 - 0.50 = -0.25<br>• Bonds 0.75 - 0.50 = 0.25 |
| Get multiplier | From column B of table 12:<br>• Equities: 0.85<br>• Bonds: 1.15 |
| Multiply | Equities: 50% × 0.85 = 42%<br>Bonds: 50% × 1.15 = 58% |
| Normalise | Total is 100% so no normalisation required. |

The final weights then are 18% NASDAQ (42% × 42%), 24% to S&P 500 (58% × 42%) and 58% to bonds. Though more uneven than before they are much less extreme than what I'd get with a single period optimiser using the same SR figures, as table 9 shows. They're also not dissimilar to my final bootstrapped weights, which also use Sharpe ratios in their calculation.

TABLE 13: HOW MUCH OF AN EFFECT DOES INCLUDING SHARPE RATIOS (SR) HAVE ON OPTIMISED PORTFOLIO WEIGHTS?

| | Single period (uses SR) | Bootstrapped (uses SR) | Handcrafted: no SR | Handcrafted: using SR |
| --- | --- | --- | --- | --- |
| US 20 year bond | 68% | 53% | 50% | 58% |
| S&P 500 equities | 32% | 27% | 25% | 24% |
| NASDAQ equities | 0% | 20% | 25% | 18% |

When I bring in Sharpe ratio estimates, handcrafting up-weights better performing assets and produces similar results to bootstrapping, but does not result in extreme portfolios like single period optimisation.

Once again, are we cheating?
Now you're using Sharpe ratios (SR) to produce your handcrafted weights it's worth reiterating that this is a mild form of in-sample back-test cheating, since you only use the final SR averaged over all data history, which you wouldn't have at the beginning of the back-test.68
Again this is a fair criticism, but the problem is not that serious. The weights are still not extreme, so the effect on back-tested SR you get is modest compared to in-sample single period optimisation. However you should still be cautious of assuming that you'd be able to achieve the back-test SR in live trading. Table 14 shows you roughly how much you should degrade back-tested returns to get realistic achievable Sharpe ratios given a particular fitting technique for a system like the one I describe in chapter fifteen.

TABLE 14: WITH HOW MANY PINCHES OF SALT SHOULD WE TREAT BACK-TESTED SHARPE RATIOS?

| | Pessimism factor |
| --- | --- |
| Single period optimisation, uses SR, in sample | 25% |
| Single period optimisation, uses SR, out of sample | 75% |
| Bootstrapping, uses SR, in sample | 60% |
| Bootstrapping, uses SR, out of sample | 75% |
| Handcrafted, no SR used, in sample | 70% |
| Handcrafted, uses SR, in sample | 65% |

The table shows what proportion of back-tested returns are likely to be available in the future. Numbers shown are for the trading system in chapter fifteen, which has four trading rule variations and six instruments. More complicated trading systems will require larger corrections for overstated in sample performance. I assume 25% of past performance was due to unrepeatable secular trends in asset prices, as I discussed in chapter two (page 52).

Now you should be able to use fitting and optimisation safely we can move on to part three: my framework for trading systems.

56. A rule with a significantly negative Sharpe ratio either has very high trading costs and should be omitted, or it is consistently wrong and so should be inverted with longs and shorts reversed before incorporating it into the portfolio (although you'll probably also want to consider the logic of your original idea before proceeding).
57. If you read the previous chapter you should recognise this as an out of sample expanding window.
58. Remember these are displayed as if all assets had the same standard deviation. So in practice roughly twice as much actual money would be allocated to bonds than shown here, due to their lower volatility.
59. For example see DeMiguel, Victor, Lorenzo Garlappi and Raman Uppal, 'Optimal versus naive diversification: How inefficient is the 1/N portfolio strategy?', Review of Financial Studies 2009.
60. To be pedantic there are some unusual portfolios where equal weights are optimal that don't fulfill these criteria, but they aren't relevant here.
61. The portfolios examined by academic researchers mostly consisted of equities from the same country, which tend to have similar standard deviation and correlations. In this situation equal weights will indeed be hard to beat.

Chapter Five. Framework Overview

NOW YOU HAVE SOME THEORY AND PERHAPS A FEW quantitative tools at your disposal you are ready to begin creating trading systems. In part three of this book I am going to describe a framework which will provide you with a template for the creation of almost any kind of strategy.

Chapter overview

| | |
| --- | --- |
| A bad example | A trading system with some fatal flaws. |
| Why use a modular framework | The reasons why a modular framework makes sense for systematic trading strategies. |
| The elements of the framework | A brief road map of the various components in the framework. |

The following chapters in part three will describe each component in more detail. In the final part of the book I'll show three examples of how this framework can be used, for semi-automatic traders, asset allocating investors and staunch systems traders.

A bad example
Here's an example of the kind of trading system you find in many books and websites.69

| | |
| --- | --- |
| Entry rule | Buy when the 20 day moving average rises over the 40 day, and vice versa. |
| Exit rule | Reverse when the entry rule is broken, so if you are long close when the 20 day moving average falls behind the 40 day and go short. |
| Position size | Never trade more than 10 Eurodollar futures, 1 FTSE contract or £10 per spread bet point. |
| Money management | Never bet more than 3% of your capital on each trade. |
| Stop loss | Set a trailing stop to close once you have lost 3% of your capital. If you find yourself triggering stops too frequently, then widen them. |

I am not going to discuss the entry or exit rule.70 However the position sizing, money management and stop loss are a mess.
Firstly why 3%? Will this generate the right amount of risk? What if I'm particularly conservative, should I still use 3%? If I don't like a particular trade that much, what should I bet? I typically have 40 positions in my portfolio, so should I be putting 40 lots of 3% of my portfolio at risk at any one time (meaning 120% of my total portfolio is at risk)? Does 3% make sense if I am using a slower trading rule?
The position sizes above might make sense for someone with an account size of perhaps £50,000 and a certain risk appetite, but what about everyone else? They might be correct when the book was written, but are they still right when we read it five years later? What about an instrument that isn't listed, can we trade it? How?
Finally, setting a stop loss based solely on your capital and personal pain threshold is incorrect.71 Someone with a tiny account who hated losing money would be triggering their very tight stops after a few minutes, whilst a large hedge fund might close a losing position after decades. Stops that would make sense in oil futures would be completely wrong in the relatively quiet USD/CAD FX market. A stop that was correct in the peaceful calm of 2006 would be absurdly tight in the insanity we saw in 2008.
The solution is to separate out the components of your system: trading rules (including explicit or implicit stop losses), position sizing, and the calculation of your volatility target (the average amount of cash you are willing to risk). You can then design each component independently of the other moving parts.
Trading rules and stop losses should be based only on expected market price volatility, and should never take your account size into consideration. Calculating a volatility target, how much of your capital to put at risk, is a function of account size and your pain threshold.72 Positions should then be sized based on how volatile markets are, how confident your price forecasts are, and the amount of capital you wish to gamble.
Each of these components is part of the modular framework which together form a complete trading system.

Why a modular framework?
Remember that I drew an analogy between cars and trading systems in the introduction of this book. Trading rules are the engine of the system. These give you a forecast for instrument prices; whether they are expected to go up or down and by how much.In a car the chassis, drive train and gearbox translate the power the engine is producing into forward movement. Similarly, you will have a position risk management framework wrapped around your trading rules. This translates forecasts into the actual positions you need to hold.
As I said in the introduction the components of a modern car are modular, so they can be individually substituted for alternatives. The trading rules and other components in my framework can also be swapped and changed.
The words module and component could imply that these are complex processes which need thousands of lines of computer code to implement. This is not the case. Every part involves just a few steps of basic arithmetic which require just a calculator or simple spreadsheet.
Let's look in more detail at the advantages of the modular approach.
Flexibility
The most obvious benefit of a modular design is flexibility. Cars really can be any colour you like, including black. Similarly my framework can be adapted for almost any trading rule, including the discretionary forecasts used by semi-automatic traders and the very simple rule used by asset allocating investors. If you don't like the position sizing component, or any other part of the framework, you can replace it with your own.
Transparent modules
It's possible to have frameworks that are nicely modular but which contain entirely opaque black boxes. Most PCs are built like this. You can replace the hard disc or graphics card, but you can't easily modify them or make your own, so you are stuck with substituting one mysterious part with another.
In contrast each component in my framework is transparent - I'll explain how and why it is constructed. This should give you the understanding and confidence to adapt each module, or create your own from scratch.
Individual components with well defined interface
If you replace the gearbox in your car you need to be sure that the car will still go forward or backwards as required. But if the drive shaft output is reversed on your new gearbox you will end up driving into your front door when you wanted to reverse out of your driveway. To avoid this we need to specify that the shaft on the gearbox must rotate clockwise to make the car go forward, and vice versa.
Similarly if you use a new trading rule then the rest of the modular trading system framework should still work correctly and give you appropriately sized positions. To do this the individual components need to have a well defined interface - a specification describing how they interact with other parts of the system.
For example in the framework it will be important that a trading rule forecast of say +1.5 has a consistent meaning, no matter what style of trading or instrument you are using.73

Getting the boring bit right
The part of the trading system wrapped around the trading rules, the framework, is something that's easily ignored. Creating it is a boring task compared with developing new and exciting trading rules, or making your own discretionary forecasts. But it's incredibly important. By creating a standard framework I've done this dull but vital work for you.
The framework will work correctly for any trading rule that produces forecasts in a consistent way with the right interface. So it won't need to be radically redesigned for any new rules. Also by using the framework asset allocating investors and semi-automatic traders can get much of the benefits of systematic trading without using trading rules to forecast prices.

Examples give you a starting point
Creating a new trading system from scratch is quite a daunting prospect. In the final part of this book there are three detailed examples showing how the framework can be used to suit asset allocating investors, semi-automatic traders and staunch systematic traders. Together these provide a set of systems you can use as a starting point for developing your own ideas.

The elements of the framework
Table 15 shows the components you'd have in a small trading system with two trading rules, a total of four trading rule variations, and two instruments. You first create a trading subsystem for each instrument. Each subsystem tries to predict the price of an individual instrument, and calculate the appropriate position required. These subsystems are then combined into a portfolio, which forms the final trading system.

Instruments to trade
Instruments are the things you trade and hold positions in. They could be any financial asset including directly held instruments such as equities and bonds, or derivatives like options, futures, contracts for difference and spread bets. You can also trade collective funds such as exchange traded funds (ETFs), mutual funds, and even hedge funds.

Forecasts
A forecast is an estimate of how much a particular instrument's price will change, given a particular trading rule variation. For example a simple equities strategy might have three forecasts: two variations on a trend following rule, each looking for different speeds of trend, and a separate equity value trading rule with a single variation. If you are trading two instruments as in table 15 then there will be a total of 3 × 2 = 6 forecasts to make.
The trading rules which produce forecasts are the engine at the heart of all trading systems used by staunch systems traders. The biggest difference between strategies will be in which rules and variations are used, and which instruments are traded. In comparison the rest of the framework will be fairly similar.
Semi-automatic traders make discretionary forecasts, rather than using systematic rules. Asset allocating investors don't try and predict asset prices and use a single fixed forecast for all instruments.

Combined forecasts
You need a single forecast of whether an instrument will go up or down in price, and by how much. If you have more than one forecast you will need to combine them into one combined forecast per instrument, using a weighted average. To do this you'll allocate forecast weights to each trading rule variation.

Volatility targeting
It's important to be precise about how much overall risk you want to take in your trading system. I define this as the typical average daily loss you are willing to expose yourself to. This volatility target is determined using your wealth, tolerance for risk, access to leverage and expected profitability. Initially we'll assume that you're putting all of your capital into a single trading subsystem, for just one instrument.

Scaled positions
You can now decide how much of the underlying asset to hold based on how risky your instruments are, how confident you are about your forecasts, and your volatility target. The positions you will calculate assume for now that you're just trading one isolated instrument, in a single trading subsystem.
At this point you've effectively got a complete trading system, but for a single instrument. Just as the cells in the human body are each individual living organisms, these trading subsystems are self-contained units, but in the next stage you'll be putting them together.

Portfolios
To get maximum diversification you'd usually want to trade multiple instruments and put together a portfolio of trading subsystems, each responsible for a single instrument. This requires determining how you are going to allocate capital to the different subsystems in your portfolio, which you will do using instrument weights. After applying this stage you'll end up with portfolio weighted positions in each instrument, which are then used to calculate the trades you need to do.

Speed and Size
This isn't a separate component in the framework, but a set of principles which apply to the entire system. When designing trading systems it's important to know how expensive they are to trade, and whether you have an unusually large or small amount of capital. Given that information, how should you then tailor your system? I'll address both of these issues in detail in the final chapter of part three.

69. This is a hypothetical example and as far as I know isn't identical to any publicly available system.
70. The rules aren't too bad, as they are purely systematic and very simple. However they are binary (you're either fully in or out) which isn't ideal, and having only one trading rule variation is also less than perfect.
71. This is recognised by most good traders. Here is Jack Schwager, in Hedge Fund Wizards, interviewing hedge fund manager Colm O'Shea: Jack: "So you don't use stops?" Colm: "No I do. I just set them wide enough. In those early days I wasn't setting stops at levels that made sense on the underlying hypothesis of the trade. I was setting stops based on my pain threshold. When I get out of a trade now it is because I was wrong. ... Prices are inconsistent with my hypothesis. I'm wrong and I need to get out and rethink the situation." (My emphasis.)
72. There are other considerations, such as the amount of leverage required versus what is available, and the expected performance of the system. I'll discuss these in more detail in chapter nine, 'Volatility targeting'.
73. It will become clear in later chapters what this consistent meaning is.

Chapter Six. Instruments

BEFORE YOU THINK ABOUT HOW YOU TRADE YOU NEED TO consider what you're going to trade - the actual instruments to buy or sell. It's likely you will know which asset classes you want to deal with, based on your knowledge and familiarity with different markets.
However there are certain instruments that should be completely avoided for systematic trading. Others have characteristics which make them worse than other alternatives, or would force you to trade them in a particular way. Finally there is often a choice of how you can access a particular market; you could get Euro Stoxx 50 European equity index exposure by buying the individual shares, trading a future, a spread bet, a contract for difference, a passive index fund or an active fund. Which is best?

Chapter overview

| | |
| --- | --- |
| Necessities | The minimum requirements that need to be met before you can trade an instrument. |
| Instrument choice and trading style | Characteristics that influence instrument choice between alternatives and how to trade particular instruments. |
| Access | Different ways to get exposure to instruments, and the benefits and downside of each. |

Necessities
There are a few points to consider when deciding whether an instrument is suitable for systematic trading.

Data availability
I'd like to be able to trade UK Gilt futures, but I don't have the right data licence so I can't get quoted prices. You can't trade systematically without access to prices and other relevant data.
At a minimum you will need accurate daily price information. Fully automated strategies that trade quickly or incorporate execution algorithms will need live tick prices. Fundamental trading strategies require yet more kinds of data. The costs of acquiring data on certain instruments, like Gilts perhaps, may be uneconomic for amateur investors.

Minimum sizes
Another future I would like to trade - but can't - is the Japanese government bond (JGB) future. The contract currently sells for around 150 million yen, which is well over a million dollars. If I put this into my portfolio the maximum position I would want is 0.1 of a contract, which obviously isn't possible. Few amateur investors will be able to trade these behemoths.
In stocks the minimum size is one share, normally costing less than $1,000, although the A class of Berkshire Hathaway shares currently sell for over $100,000. Even for cheaper stocks, it may not be economic to trade in lots of less than 100 shares.
Minimum sizes reduce the granularity of what you can trade. Your positions become binary - all or nothing (in the case of JGBs, always nothing). This is an important subject and I will return to it in chapter twelve, 'Speed and Size'. As you'll see in that chapter this problem also affects the number of instruments you can hold in your portfolio.

Why do prices move?
Do you know why bonds, equities and other instruments go up, or down, in price? "More buyers than sellers" is not an acceptable answer! I personally think it's important to have an understanding of what makes a market function; whether it be interest rates, economic news or corporate profits. This is vital if you're going to design ideas first trading rules.
It's also important to understand market dynamics once your system is running, if you want to avoid unpleasant surprises in markets that have become dysfunctional. As I'm redrafting this chapter, the Swiss government has just removed the peg which had held since 2011 fixing their currency at 1.20 to the euro, resulting in a massive Swiss franc (CHF) appreciation against all currencies. Thousands of traders including large hedge funds and banks were on the losing side, including many who were trading systematically.
Fortunately I wasn't trading the EUR/CHF or USD/CHF FX pairs. For me there didn't seem any point in trying to make systematic forecasts, since I knew the market was controlled by central bank intervention rather than the normal historic factors driving prices in the back-test. Keeping abreast of markets will help you to avoid similarly dangerous instruments.

Standard deviation
There is another reason why I excluded Swiss FX positions from my systematic trading strategies, which was the extremely low volatility of prices whilst the peg was in place. In principle my framework can deal equally well both with assets whose returns naturally have low standard deviations and those that are very risky. It can also cope with changes in volatility over time.
However instruments which have extremely low risk like pegged currencies should be excluded. Firstly, when risk returns to normal it is liable to do so very sharply, potentially creating significant losses. Secondly, these positions need more leverage to achieve a given amount of risk, magnifying the danger when they do inevitably blow up. Even if you don't use leverage they will limit the risk your overall trading system can achieve.74 Finally, they also tend to be more costly to trade, as you will discover in chapter twelve, 'Speed and Size'.

Instrument choice and trading style
With your pool of available instruments narrowed by excluding those which don't have the necessary attributes mentioned above, you need to decide which of those remaining you prefer to trade. These characteristics will also influence how you'll trade the instruments you've chosen.

How many instruments?
I like my portfolio of instruments to be as large and diversified as possible, as long as I don't run into issues with minimum sizes, for example as I would do with Japanese government bonds. The maximum number of instruments you can have will depend on minimum sizes, the value of your account and how much risk you're targeting (which you'll learn about in chapter nine, 'Volatility targeting').
In chapter twelve, 'Speed and Size', you'll see how to calculate the point at which you could run into problems with minimum instrument size. You will then be able to work out what size of portfolio makes sense.
Then in part four I will give some recommended portfolios in each example chapter, which have been constructed to be as diversified as possible given the level of the volatility target and the available instruments.

Correlation
If you already owned shares in RBS and Barclays then the last thing you would want to add to your portfolio is another UK bank like Lloyd's. Generally you should want to own or trade the most diversified portfolio possible, where the average correlation between the assets is lower than the alternatives. If there are a limited number of instruments that you can fit in your portfolio then it makes sense to pick those with lower correlations.

Costs
Given the choice between two otherwise identical instruments you should choose the cheapest to trade. So, if you can, use a cheap FTSE 100 future rather than an expensive spread bet to get exposure to the UK equity index.75 Instruments that are expensive to trade are clearly less suitable for dynamic strategies, particularly those that involve faster trading.
Sometimes you have to trade an expensive instrument, if it's the only way of accessing a particular asset. In this case you should trade it more slowly. There is however a maximum acceptable cost depending on the type of trading that you're doing, so some instruments will be completely unsuitable. Because the cost of trading is so important it will be covered in great detail in chapter twelve, 'Speed and Size'.

Liquidity
Closely related to costs is liquidity. Less liquid instruments are likely to be more expensive to trade quickly or in larger amounts. This is more of a problem for large institutional investors and those trading fast. Liquidity is not constant and can reduce quickly in times of severe market stress, particularly for non exchange traded 'over the counter' instruments, as in the Credit Default Swap derivatives markets in 2008.
Again chapter twelve, 'Speed and Size', will explain how those with larger account sizes will need to understand costs and liquidity better than small investors.

Skew
Should you avoid negative skew in your portfolio from instruments like holding short VIX (US equity volatility index) futures? Remember I covered the skew of assets and trading rules in chapter two, 'Systematic Trading Rules'. Static strategies will inherit the skew of their underlying instruments, but the skew of a dynamic strategy also depends on the style of your trading rule. So using a positive skew rule like trend following on a negative skew asset will alleviate some of the danger.
As you will see in chapter nine, 'Volatility targeting', you need to be extremely careful if the overall returns of your trading system are expected to have negative skew. Instruments with extreme negative skew will often have very low standard deviation for most of the time, and should be excluded on those grounds.

Access
Finally you need to choose the route by which you access the underlying assets you're going to trade.

Exchange or OTC
Does your instrument trade on an exchange like shares in General Electric and Corn futures, or over the counter (OTC) like foreign exchange (FX)? There are often different ways of trading the same underlying asset, some via exchange, others OTC. So a spread bet on the CHF/USD FX rate is OTC, whilst the Chicago future on the same rate is exchange traded.
If you have a choice then, all other things being equal, should you trade on exchange or OTC? In the January 2015 Swiss franc meltdown traders using OTC brokers suffered a variety of difficulties, including dealers not accepting orders or displaying quotes, trades not being honoured and fills re-marked after the fact, and in extreme cases potential account losses as brokers went into liquidation.
Those who traded the CHF/USD future had difficulty finding deep liquidity, but otherwise the market operated as normal. In conclusion it's normally better to trade on exchange if you can.

Cash or derivative
'Cash' is simply where you own the underlying asset directly - perhaps a share in British Gas or a bond issued by General Electric. Alternatively you can own a derivative on an asset, like a future, Contract for Difference or spread bet.76 The main advantage of derivatives is that they offer straightforward leverage. Without leverage it might be difficult to reach your volatility target, which will reduce the returns you can earn. There may also be different tax treatments; in the UK for example spread bets are treated as gambling, which means winnings are tax free but losses aren't deductible.
Various types of derivatives may have different trading costs, and also have different minimum sizes, liquidity and market access. For example a FTSE 100 future is cheaper to trade and more liquid than the corresponding spread bet. It also has the advantage of being accessed via an exchange, whereas the spread bet is OTC. But the future has a larger minimum size which precludes its use by smaller investors.

Funds
Other options for trading the FTSE 100 are to buy an index tracker like an exchange traded fund (ETF). These are collective funds - instruments which buy you a share in a portfolio of assets. As well as ETFs, collective funds include US mutual funds, UK unit trusts and investment trusts. Normally for systematic trading you will be interested in passive funds like index trackers. These contain baskets of assets weighted to match an index like the FTSE 100 or S&P 500.
Passive funds normally have relatively low annual fees and minimum sizes, but frequently cost more than the relevant derivative to trade. But they can be useful instruments when leverage can't be used, or when a market can't be accessed another way.
In some cases you might want to use active funds, where the weights to different assets are determined by the fund manager. This might make sense if there is no relevant passive fund or derivative, but fees are higher on active funds, and the presence of any compensating manager skill or alpha is very hard to prove.
Collective funds can have quirks such as daily remarking, tax treatment, internal leverage and discounts to net asset value which you should fully understand before using them.

Summary of instrument choice

| | |
| --- | --- |
| Data availability | At a minimum you need daily price data to trade an instrument systematically. For fundamental strategies you also need other relevant data, e.g. price:earnings if you're using an equity value rule. |
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

Now you know what you are going to trade, the next step is to think about how. So the next chapter will cover the business of forecasting prices.
___
74. I'll return to this topic in chapter nine, 'Volatility targeting'.
75. I'll explain why the spread bet is more expensive in chapter twelve, 'Speed and Size'.
76. I've deliberately excluded options and other non-linear derivatives from this list, since these can't be used casually as substitutes for the underlying assets.