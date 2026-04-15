12
Techniques for Improving the Robustness of Alphas
By Michael Kozlov
INTRODUCTION
The main goal of alpha research is to predict and try to outperform the market. However, most investors desire not only returns but also low risk exposure and some confidence in their ability to anticipate trading results. With these requirements in mind, we have defined a robust alpha.
A robust alpha should have the following properties:
• Invariance under modification of the traded universe: An alpha should reflect a statistical property that is independent of the choice of specific instruments to trade. Changes to the instrument set are frequently imposed by the market as a result of regulatory changes, customer preferences, liquidity decreases, short bans, etc.
• Robustness to extreme market conditions: An alpha should not have excessively sharp declines in any of its performance benchmarks. The most common benchmarks used for alpha performance measurement include information ratio, maximum drawdown, and return.
METHODS FOR ROBUSTNESS IMPROVEMENT
In this section, we will introduce the most common and established techniques for improving the robustness of an alpha. In general, our goal is to ensure stable alpha performance that is not unduly affected by input data outliers or other small departures from model assumptions. Methodologies for robustness improvement can be classified into three categories: ordering methods, approximation to normal distribution, and limiting methods. Below we will discuss all three methods in detail.
Ordering Methods
The powerful motivation for applying ordering methods in alpha research is to improve the alpha property of invariance, meaning that the test results do not change when the input data or traded universe is transformed in some way.
An ordinal scale of measurement is one that conveys order alone. These scales indicate only that one value is greater or less than another, so differences among ranks do not have meaning.
Generally speaking, ordering-based procedures are a subset of nonparametric methods, which in many circumstances have advantages in robustness over parametric methods. They are preferred when certain assumptions of parametric procedures (for example, t- and F-tests) are grossly violated. That may happen, for example, when the normality assumption is not satisfied by a dataset with extreme outliers. In addition, alphas based on nonparametric methodologies by nature require fewer assumptions and control parameters than their parametric alternatives.
Ranking: Ranking is an operation that replaces a vector's elements with their ranks under some sorting criterion. Usually, the elements of the vector are rescaled to be in the interval [0,1]. If two values are the same, they are supposed to have the same rank, equal to the average of their corresponding positions.
Ranking can be used to define the Spearman's rank correlation (Spearman 1904). In many cases, the Spearman correlation is much more stable than the Pearson correlation measure (Pearson 1895). For instance, the Pearson correlation is known to be unstable for nonstationary and/or nonlinear inputs.
It is obvious that any statistics based on the ranks of the data must be invariant to monotone transformations
because such transformations do not affect the relative rankings of observations. Thus, rank-based statistics do not depend on whether the outcome is measured on the original scale or on any other arbitrary scale.
Quantiles approximation: Quantiles are points taken at regular intervals from the cumulative distribution function of a random variable. Splitting a set of ordered data into equal-size data subsets is the motivation for q-quantities; the quantities are the data values marking the boundaries among consecutive subsets.
For example, ordinary least squares regression may be unstable for nonstationary and/or nonlinear inputs. However, it can be replaced by least quantile of squares (LQS), in which the objective is to minimize some quintile of the squared residuals. Among the various LQS methods, the most popular is median squares minimization.
Approximation to Normal Distribution
The normal distribution is the random variable distribution defined by the following probability density function:
f(x|μ,σ^2) = 1/(sqrt(2πσ^2)) * e^(-(x-μ)^2 / (2σ^2))
where μ is the mean of distribution, σ is the standard deviation, and σ2 is the variance. The normal distribution has special importance in statistics because of the so-called central limit theorem, which states that under certain conditions the sum of many random variables will have an approximately normal distribution.
We will illustrate several methods of transforming an arbitrary distribution function to an approximately normal distribution function. When the underlying distribution is
roughly normal but contaminated with outliers and heavy tails, the following robust methods can help maintain stable performance, even under extreme market conditions.
Fisher Transform formula: Assuming that a random variable x is bounded by 1, the Fisher Transform can be defined as follows:
F(x) = 1/2 * ln((1 + x) / (1 - x)) = arcth(x)
If F(x) is the Fisher transformation of x and N is the sample size, then F(x) approximately follows a normal distribution with standard error 1/sqrt(N-3).
Z-scoring: Z-scoring of data results in a distribution with zero mean and unit standard deviation. The Z-score is defined as follows:
Z = (x - μ) / σ
In other words, the Z-score represents the distance between the raw score and the population mean in units of the standard deviation.
Limiting Methods
Extreme values can have a significant and generally harmful effect on the statistical properties of observed quantities. Therefore, one aim of robust methods is to reduce the impact of outliers.
Trimming: With trimming, we simply remove a certain fraction of the data above or below some threshold.
Winsorizing: Winsorization is a transformation that limits extreme values in the data to reduce the effect of possibly spurious outliers, as originally suggested by
Hastings et al. (1947) and later argued more systematically by Rousseeuw and Leroy (1987). Winsorizing is similar to trimming, but we replace the extreme values with cutoff values rather than throwing them out.
Let us illustrate how trimming and winsorizing will affect the calculation of simple estimators on a sample set of numeric data {3,5,7,10,100}. Consider the mean, median, k-trimmed mean, and k-winsorized mean as defined below.
a. mean: arithmetic mean of sample data
mean = (3 + 5 + 7 + 10 + 100) / 5 = 25
b. median: the value separating the higher half of a data sample from the lower half
median = 7
c. k-trimmed mean: trim a given proportion α from both ends of the dataset and then take the mean.
20% trimmed mean = (5 + 7 + 10) / 3 = 7.33
d. k-winsorized mean: replace a proportion k from both ends of the dataset by the next closest observation and then take the mean.
20% winsorized mean = (5 + 5 + 7 + 10 + 10) / 5 = 7.4
From the above example, we can see that both the k-trimmed mean and the k-winsorized mean are much more stable with regard to outliers than the arithmetic mean. The k-trimmed mean and the k-winsorized mean are also very close to the median, which is a well-known robust estimator.
All of the above estimators (mean, median, k-trimmed mean,
and k-winsorized mean) can be considered particular cases of L-statistics, or linear combinations of order statistics. For example, for particular sample values the smallest order statistic is the minimum of the sample:
X_{(1)} = min{X_1, ..., X_n}, and the largest order statistic is the maximum of the sample: X_{(N)} = max{X_1, ..., X_n}. The kth order statistic is the kth data point when the points are ordered.
CONCLUSION
As argued by Bertsimas et al. (2004), robust methods can significantly improve several benchmarks that measure alpha behavior in extreme market conditions. These days, more and more practitioners are exploiting the advantages offered by robust methodologies developed over the past decades. Most standard statistical software packages include a variety of tools for robust data analysis.
It's important to remember that robust methods assume that the underlying distribution is roughly normal but contaminated with outliers and heavy tails. The methods can produce misleading results if they are applied to data that is inherently skewed or if a large proportion of the data is identical in value.
For further details about robust methods, refer to Robust Statistics by Peter J. Huber and Elvezio M. Ronchetti (2009).
