19
Financial Statement Analysis
By Paul A. Griffin and Sunny Mahajan
Financial statements are formal records of a company's financial health for a given period of time or at a given point in time. Security analysis, popularized by Benjamin Graham and David Dodd in their 1934 classic investing tome (2009), is the in-depth study of these statements on a per company basis to gauge the potential for excess returns based on a company's underlying qualities. This analysis is used by fundamental value investors, Warren Buffett being the most famous practitioner. It contrasts with studying the movements and order flow of stock prices, as discussed by Edwin Lefèvre in Reminiscences of a Stock Operator (2006), or other technical analysis approaches, such as momentum-based strategies, which make bets based on an expectation that price trends will continue into the future (see Chan et al. 1996 and references therein).
Financial statement analysis attempts to systematically measure the effect of factors computed using these statements and to determine their ability to predict future returns; investors can use it to rank, sort, and filter companies to seek to create a portfolio with improved financial strength. The opinion that financial statement analysis can be leveraged to generate excess returns was initially received with skepticism because of the prevailing orthodoxy of the efficient market hypothesis (EMH), which postulates that in an efficient market, current prices reflect all available information. However, subsequent works on multiple factors constructed from a diverse and logical selection of earnings information demonstrated violations of the EMH over long periods of time (see, for example, Abarbanell and Bushee 1997; Bartov and Mohanram 2004; Beneish and Nichols 2009; Chan et al. 2001; and Piotroski 2000).
Traditional financial statement analysis typically results in a stock screen generating a long-only, low-turnover portfolio with a reduced investment universe selected on the basis of companies' fundamental characteristics. Modern analysis, however, uses financial statements to derive quantitative portfolios with stock exposures based on fundamental ratios and derived metrics – and possibly subject to other constraints without specifically reducing the investment universe. Under these more contemporary terms, investors try to use fundamental factors as predictors in a multifactor regression or features in a machine learning algorithm.
Financial statement analysis, along with additional data sources associated with market performance, analyst recommendations, and earnings surprises, can be combined to identify alphas.
This chapter is not designed to cover the entire subject of fundamental analysis; a more comprehensive overview of the subject is provided in the next chapter. This chapter is intended to serve as a basic introduction to the subject and may, we hope, provide some inspiration for future research.
BASICS
Companies release financial statements on a quarterly and annual basis. There are four main statements: balance sheets, income statements, cash flow statements, and statements of shareholders' equity.
Balance sheets are a snapshot at a single point in time of a company's assets, liabilities, and shareholders' equity. Unlike the balance sheet, which pertains to a given moment, income statements provide information about a company's financial performance over a specific accounting period. The cash flow statement provides data on the cash inflows and outflows from a company's operations and external investment sources for a given period. The statement of shareholders' equity shows changes in the interests of the company's shareholders over time.
Investors use these statements to evaluate a company's risks, performance, financial health, and prospects. Note that in this context, preliminary quarterly announcements and the subsequently filed statements can differ; the audited annual financial statements are generally considered to be the most authoritative.
THE BALANCE SHEET
The basic equation of accounting, also called the balance sheet equation, is represented by the balance sheet in Table 19.1 and is expressed as follows:
Table 19.1 The balance sheet equation
Balance sheet YYYYMMDD
Assets Liabilities + Equity
Current assets Current liabilities
Other assets Long-term debt
Intangible assets (goodwill, etc.)
Total assets Shareholders' equity

Assets = Liabilities + Equity
Note that this balance sheet is for a given date and provides a snapshot of the company's well-being. By comparing snapshots, investors can find changes that could cause a repricing of the company's outstanding equity. Total assets are typically used as a normalizing factor to make the values of other factors comparable among different companies or to compare snapshots of the same company at different times. For US companies, the value of total assets includes the intangible asset known as goodwill, defined as what a company pays for another company above book value. Though goodwill contains items such as branding, investors should generally consider whether to discount the goodwill included in the total assets as a normalizing factor.
The following well-known factors constructed from the balance sheet were positively correlated with future returns from 1976 to 1996, as observed by Piotroski (2000):
• Increased liquidity (current assets over current liabilities)
• Improved sales over total assets
• No equity issuance
• Less long-term debt
THE INCOME STATEMENT
The income statement reflects changes in the balance sheet from one time period to the next, as shown in Table 19.2. Most companies use accrual-based accounting, so the income statement does not reflect the movement of cash but, rather, the accrual of obligations to be paid. For example, if a company signs a multiyear contract to supply products, it recognizes the revenue when it fulfills each obligation in the contract, not when the other party transfers cash to an account.
Table 19.2 The income statement
Income statement YYYYMMDD
Net sales (sales) A
Interest income B
Cost of goods C
Operating expenses D
Income taxes E
Gross margin A - C
Income from operations A - C - D
Gross income A + B
Net income A + B - C - D - E
The following factors based on the income statement were positively correlated with future returns in the US from 1976 to 1996, according to Piotroski (2000):
• Net income > 0
• Improved net income over total assets
• Improved gross margin
THE CASH FLOW STATEMENT
The cash flow statement, as shown in Table 19.3, describes the sources of the change in a company's cash balance from one period to the next. The following factors were positively correlated with future returns in the US from 1976 to 1996, according to Piotroski (2000):
Table 19.3 The cash flow statement
Cash flow statement YYYYMMDD
Cash balance A
Cash from operations B
Borrowings C
Stock sale D

Purchases E
Taxes F

Cash flow B + C + D - E - F
Cash balance A + B + C + D - E - F
• Cash from operations > 0
• Cash from operations > net income
GROWTH
The factors above are focused on finding quality in company performance. However, investors may also be interested in growth prospects.
A similar regression analysis for growth stocks was performed by Chan et al. (2001) and Bartov and Mohanram (2004); they found signals that correlated with future returns specifically for growth stocks (stocks with low book-to-market ratios) from 1979 to 1999:
• Net income/total assets > industry median
• Cash flow/total assets > industry median
• Net income variance < industry median
• Gross income variance < industry median
• R&D expenses/total assets > industry median
• Capital expenditure/total assets > industry median
• Advertising expenses/total assets > industry median
R&D, capital, and advertising expenses are separate items inside the operating expenses line item of the income statement, as indicated in Table 19.4. Growing companies will build out these areas with expectations of improved future sales.
Table 19.4 The income statement: operating expenses
R&D expenses D1
Capital expenses D2
Advertising expenses D3
Other operating expenses D4
Operating expenses D = D1 + D2 + D3 + D4
CORPORATE GOVERNANCE
Management monitors and seeks to improve company performance using metrics, and market participants will tend to reward the stock price when they observe improvements in some of these. Metrics positively correlated with future returns, according to Abarbanell and Bushee (1997), are:
• Reduced inventory per unit sales
• Improved accounts receivable per unit sales
• Improved sales minus change in gross margin
• Reduced administrative expenses per unit sales
• Improved tax rate
• Earnings quality – change to the use of FIFO versus LIFO
• Audit qualification – change to qualified auditing
• Sales per employee
NEGATIVE FACTORS
Some factors are specifically useful for isolating a short portfolio. Beneish and Nichols (2009) suggest searching for earnings manipulation, a history of mergers, equity issuance, and other forms of management efforts to improve the reported earnings or cash flow without actually improving the core business. Factors negatively correlated with future returns include:
• Higher net sales than free cash flow
• Low book to price
• High sales growth
• Low cash flow from operations to price
• Acquisition in past five years
• Equity issuance > industry average over two years
Nissim and Penman (2003) show that high financial leverage, defined as net financing debt over common equity, is negatively correlated with operating profitability; the definition of financial leverage excludes operating liabilities. High long-term financial leverage can be a signal of pending liquidity issues or even insolvency. A well-known case study of the misguided application of financial leverage is the history of the hedge fund firm Long-Term Capital Management. Also, the Enron Corporation accounting scandal was based on the use of special-purpose vehicles to keep long-term debt off the balance sheet, and the corrected accounting of debt led to the company's insolvency. Generally, additional leverage adds risk that can lead to either higher profits or the risk of ruin. Therefore, it is wise to analyze leverage and debt in conjunction with other factors to find the combinations that indicate meaningful positive or negative correlations with future returns.
SPECIAL CONSIDERATIONS
When analyzing financial statements, investors must factor in the industry of the company being studied. In commodity-based industries, for example, the underlying commodity price contributes significantly to sales, so sales increases are not necessarily a measure of improved company performance. Banks have different reporting requirements and should be given special treatment. The phase of the economic cycle may affect the correlation of debt with price appreciation and significantly impact factors closely associated with growth.
FACTORS AS SCREENS
In the investment literature, the most common use of factors is to construct a universe screen, particularly by the mechanism of assigning a score of +1 to a company when it passes a particular test, then combining the scores over all factors and taking a long position on the highest-rated companies. This is generally a reasonable fusion method in the absence of a more significant statistical analysis, according to Kahneman (2011).
CONVERTING FACTORS TO ALPHAS
Note that most of the scores are based on the rate of change, which generally subtracts the latest statement data from the previous year(s); otherwise, seasonality will contaminate direct quarter-over-quarter comparisons. Statement data may be delayed for alpha analysis, and investors should be careful to note the time delays in the data used for alpha generation. Point-in-time financial data provides significantly more-realistic results (and worse backtesting results) because it removes the forward bias associated with statement refilings.
More sophisticated statistical analyses, such as regressions and factor correlation analysis, may produce better alphas. Investors can also employ machine learning techniques such as genetic algorithms to find good factor combinations; this may be particularly successful if the inputs are based on a thorough understanding of the factors' meanings. The market rewards strategies based on new meaningful factor combinations, so researchers should think creatively and continually scan the literature for the latest ideas.
CONCLUSION
Financial statement analysis allows analysts to identify trends and discern investment opportunities by comparing key performance metrics over multiple time periods and statement types. Many financial signals have been observed to be correlated to excess returns and can be effectively leveraged in an investment process.
Though financial statements do not directly reflect all the information that indicates a company's potential, they do contribute a key piece of the investment puzzle. In the pursuit of alphas, the meaningful interpretation and analysis of financial statements can be a solid basis for informed investment decisions.