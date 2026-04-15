11
The Triple-Axis Plan
By Nitish Maini
The world of quantitative investing is growing extremely rapidly. Quants are developing new ways of predicting market fluctuations by using mathematics, computer programming, and an ever-proliferating array of datasets. Discovering new alphas can be a formidable challenge, however, particularly for new quants. An efficient exploration of the vast universe of possible alphas – what we call the alpha space – requires a structured strategy, an anchoring point, and an orientation technique, otherwise known as the Triple-Axis Plan (TAP).
TAP can help new quants define the alpha space by providing a framework for conceptualizing the search for alphas. It can also help more-experienced quants, who have the ability to define the entities that constitute each axis and then analyze existing alphas in their portfolios, to target their efforts with greater efficiency.
New quants can easily be overwhelmed by the challenge of trying to develop alphas. They ask themselves, “How do I find alphas? How do I start the search?” Even experienced quants working with many alphas can miss key components required to build a robust, diversified portfolio. For instance, one of the most difficult aspects of alpha portfolio construction is the need to optimize the level of diversification of the portfolio. In automated trading systems, decisions on diversification make up a major area of human intervention. It's not easy to visualize the many pieces of the portfolio, which contain hundreds or thousands of alphas, and their interactions.
TAP emerged from those concerns. When new quants start conducting alpha research, many begin by searching the
internet for articles about developing alphas. Most of those articles focus on reversion and momentum, and as a result, beginners may initially spend a lot of time building reversion or momentum alphas. But as new quants grow more skilled, they begin to wonder whether they are actually creating much value when they add a new alpha to their portfolios. Though they think they are diversifying their portfolios, they may just be developing the same kinds of alphas over and over again. Although they may appear to have low correlation, variants of the same alpha types tend to have the same failure modes and do not provide the full benefit of a truly diversified portfolio.
Nearly everyone falls into this trap when they begin to research alphas. Every successful quant has a gold mine; he digs deeper and deeper in his mine to extract as much as he can. One person develops a very strong momentum site; another has a very strong fundamental site; a third builds a very strong reversion site. They often forget, however, that there are multiple gold mines out there. After they play out one area, they need to move on to find and explore other mines.
TAP is really just a tool to organize the complex, multidimensional alpha space. It offers a number of advantages for portfolio diversification. The alpha space is vast, with a high and growing number of degrees of freedom, and there is an almost unlimited number of possible alphas, with each region or cluster of alphas possessing different topographies that require discovery and exploration. A quant has a plethora of choices. She can make predictions to trade over intervals ranging from microseconds to years. She can make predictions on different asset classes, most commonly equities, bonds, commodities, and currencies. But the set of possible elements that a quant can manipulate is growing all the time – more datasets, more parameters, more ideas.
With the available data expanding at such rapid rates – in fact, because there's so much data – it is important to develop a plan to organize this complex landscape that has a reasonable probability of success. Every successful quant needs a strategy to identify viable signals within a world of noise, to target specific regions within the possible universe, and to select the kind of data and the specific financial instruments that are most appropriate to the purpose. You need a model to structure your search. TAP is such a model.
THE TAP
The process of searching for alphas in this complex landscape can vary widely as a function of the ideas behind the alphas and the desired objective function, which may include attributes of the signal, such as turnover, trading frequency, or universe of tradable instruments. To make this easier to visualize, TAP structures alphas within an asset class in a three-dimensional space (see Figure 11.1).
[Graph: Figure 11.1 The three axes of the Triple-Axis Plan (Performance Parameters, Ideas & Datasets, Regions & Universes)]
The ideas used to develop alphas may range from traditional indicators, like reversion, momentum, or pairs trading; to less common ones, like machine learning, lead-lag, or seasonality. With increasing computing power, the number of datasets that we can use to implement these ideas has grown so much that we can measure the diversity of a pool of signals by the number of different datasets used. The most widely used datasets include price and volume data, company fundamentals, analyst recommendations, stock sentiment, social media, and options, but there are many others. These ideas can be generated and implemented on different groups of financial instruments in different regions. The market capitalization of individual stock exchanges and the regulatory environment in a specific region or country usually define the choice of region for a quant. The US and Europe have traditionally seen the heaviest trading, although Asian markets have attracted increasing interest in recent
years. Trading instruments may be defined in terms of their liquidity, classification characteristics like sector or industry, or other criteria, depending on the alpha idea.
To seek success under different market conditions, a quant can construct a diverse, robust portfolio by developing alphas that try to achieve one or multiple objective functions, usually related to attributes that explain their performance. Quants aim to generate profits by maximizing the Sharpe ratio and or by minimizing drawdowns and trading costs. The TAP approach is one way to orient yourself in this world, with each axis providing a different lens through which to focus your research. Many elements can be added to each axis, depending on the approach. Table 11.1 provides a simplified schematic of the three axes. The possible constituent entries in each axis can be much more extensive, of course.
Table 11.1 Some of the ideas, datasets, regions, universes, and performance parameters that TAP spans
The three axes
Ideas & datasets Regions & universes Performance parameters
Ideas
• reversion
• momentum
• seasonality
• learning
• lead-lag
Regions
• US
• Europe
• Asia (Japan or ex-Japan)
• Americas
• global
• high returns
• high Sharpe ratio
• lower costs
• lower drawdowns
Datasets
• fundamental
• analyst
• sentiment
• social media
• options
Universes
• can be defined using the liquidity profile, such as TOP50, TOP100, TOP200, TOP1500
• any particular sector or industry
• any selected instrument or group of instruments
IMPLEMENTING TAP
TAP employs a relatively simple, mechanical process that both reflects and organizes the complex financial reality of alpha space. It allows a strategist to fill in the blanks on the three axes, thus revealing possible missing components of the portfolio.
TAP operates on three levels. The first involves identifying an initial area to focus on. The user can start with a relatively generic focus on a single axis – say, on momentum as an idea; or on a particular regional area, like the US or Europe; or on performance parameters such as a high Sharpe ratio or minimal drawdowns. The second level involves refining the focus by systematically filling in the elements of the other axes. TAP allows the quant to choose a target on one axis and maintain the flexibility to manipulate the other two axes. Working on each target independently helps the quant develop skills and gather the knowledge necessary to build alphas in that area. The third level involves execution: implementing the algorithm in code, testing the initial idea, and then going back to refine the basic concept by working across the three axes.
Consider this relatively simple example. Suppose that a quant is exploring ideas that might work in a predominantly liquid universe of stocks. He chooses to focus first on the Regions & Universes axis and selects the liquid universe – the top 500 or 300 companies in the US. Later, to diversify geographically, he will need alphas and strategies for Asia and Europe as well as the US. This should be relatively easy because after already developing momentum and reversion alphas and becoming familiar with the properties of liquid universes, it is natural to apply this knowledge to Europe and Asia. At the same time, the researcher realizes that it is not enough to focus only on reducing the cost of the alphas or increasing their Sharpe ratios; it is also important to generate high returns. Getting higher returns, however, often requires a trade-off against the effects of the other parameters. Thus, it takes a higher level of skill to seek higher returns. Now the quant can iterate again through his previous work and continue aiming to develop a high-return momentum alpha, a high-return reversion alpha,
and a high-return liquid alpha.
To achieve a desired level, diversification requires systematically mastering the use of TAP's three axes:
• The choice to focus on a momentum alpha freezes the Ideas & Datasets axis. In this case, the next steps are to diversify on the other two axes by choosing different Regions & Universes of financial instruments to develop momentum alphas, and to target alphas to optimize different kinds of performance parameters.
• Similarly, the choice to develop an alpha on the US financial sector fixes the Regions & Universes axis but retains the flexibility to use different ideas or datasets to optimize different performance parameters.
• The choice to develop a high-return alpha fixes your Performance Parameters axis, leaving the flexibility to vary the other two axes on any kind of dataset, idea, region, and universe to seek the desired return target.
The complexities of financial markets allow for a vast range of granularity and precision, which are what provide richness to the alpha space and excitement to the challenge of finding new alphas. It is important to recognize that there is no single fail-safe solution. The world of finance is shaped by idiosyncratic differences among individuals' valuations of assets, returns, and risk. Therefore, potential value lies in exploring the known landscape as extensively as possible, even in areas often dismissed as noise; they could potentially turn out to be infinite sources of knowledge. The quant just needs to make deliberate choices about where to begin that search and how to organize the effort.
CONCLUSION
TAP is a tool that visualizes the various dimensions that affect alpha performance. As a result, it can provide a quant with greater clarity and insight into the complex alpha space. TAP
is not a secret weapon that ensures success, but it does help less experienced quants begin their search and understand the underlying issues, and it helps more-experienced strategists enhance the diversification of very complex portfolios of alphas. To be most effective, TAP should be integrated into all the necessary steps of alpha development, refining, testing, and execution.
