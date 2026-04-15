8
Alpha Correlation
By Chinh Dang and Crispin Bui
Alphas are evaluated by many different metrics, such as the information ratio, return, drawdown, turnover, and margin. These metrics are derived mainly from the alpha's profit and loss (PnL). For example, the information ratio is just the average returns divided by the standard deviation of returns. Another key quality of an alpha is its uniqueness, which is evaluated by the correlation coefficient between a given alpha and other existing alphas. An alpha with a lower correlation coefficient normally is considered to be adding more value to the pool of existing alphas.
If the number of alphas in the pool is small, the importance of correlation is low. As the number of alphas increases, however, different techniques to measure the correlation coefficient among them become more important in helping the investor diversify his or her portfolio. Portfolio managers will want to include relatively uncorrelated alphas in their portfolios because a diversified portfolio helps to reduce risk. A good correlation measure needs to identify the uniqueness of one alpha with respect to other alphas in the pool (a smaller value indicates a good uniqueness). In addition, a good correlation measure has the ability to predict the trend of movement of two alpha PnL vectors (time-series vectors). The correlation among alphas can be computed based on alpha PnL correlation or alpha value correlation.
ALPHA PnL CORRELATION
Given two alpha PnL vectors (we use bold letters for vectors):
P_i = [P_{i1}, P_{i2}, ..., P_{in}]^T ∈ R^n (1)
P_j = [P_{j1}, P_{j2}, ..., P_{jn}]^T ∈ R^n
where P_{it} and P_{jt} denote the PnLs of i^{th} and j^{th} alphas on the t^{th} day, n is the number of days used to measure correlation, and T denotes the matrix transposition. Note: tests usually select the number of days for correlation as two or four years instead of a full history, to save computational resources.
Pearson Correlation Coefficient
The Pearson correlation coefficient, also known as the Pearson product-moment correlation coefficient, has no units and can take values from -1 to +1. The mathematical formula was first developed by Karl Pearson in 1895:
r = cov(P_i, P_j) / (σ_{P_i} σ_{P_j}) (2)
where cov(P_i, P_j) = E[(P_i - μ_{P_i})(P_j - μ_{P_j})] is the covariance and σ_{P_i} and σ_{P_j} are the standard deviations of P_i and P_j, respectively. For two vectors of PnLs, the coefficient is computed by using the sample covariance and variances. In particular,
r = Σ_{t=1}^n (P_{it} - \bar{P}_i)(P_{jt} - \bar{P}_j) / sqrt(Σ_{t=1}^n (P_{it} - \bar{P}_i)^2 Σ_{t=1}^n (P_{jt} - \bar{P}_j)^2) (3)
The coefficient is invariant to linear transformations of either variable. If the sign of the correlation coefficient is positive, it means that the PnLs of the two alphas tend to move in the same direction. When the return on P_i is positive (negative), the return on P_j has a tendency to be positive (negative) as well. Conversely, a negative correlation coefficient shows that the PnLs of the two alphas tend to move in opposite directions. A zero correlation implies that there is no relationship between two PnL vectors. Figure 8.1 shows the variation of maximum correlation as a function of trading signals, using two years' worth of data.
[Graph: Figure 8.1 Variation of maximum correlation as a function of trading signals]
Alphas seek to make predictions about the future movements of various financial instruments. As a result, the analysis needs to be extended into a time series, which includes a sequence of random variables with the time index. In the case of an alpha PnL vector, the observation is the profit (+) or loss (-) of the alpha in one day. Below we briefly review the dot product, then discuss the temporal-based correlation.
Temporal-Based Correlation
The dot (inner) product is defined as the sum of the products of the corresponding entries of the two sequences of numbers.
P_i · P_j = |P_i| |P_j| cos(θ) (4)
where |P| is the modulus, or magnitude, of the PnL vector and θ is the angle between the two vectors. One important application of the dot product is to find the angle between two vectors because the angle θ can be found via
cos(θ) = P_i · P_j / (|P_i| |P_j|) = Σ_{t=1}^n P_{it} P_{jt} / (sqrt(Σ_{t=1}^n P_{it}^2) sqrt(Σ_{t=1}^n P_{jt}^2)) (5)
When the angle is zero, the two PnL vectors fall on the same line and cos(θ) = ±1. When the angle is π/2, the vectors are orthogonal and cos(θ) = 0.
The temporal-based correlation considers each alpha's PnL vector as a time-series sequence and assigns weight to the values on each day. The correlation between two PnL vectors is thus defined as:
r = Σ_{t=1}^n w_t P_{it} P_{jt} / (sqrt(Σ_{t=1}^n w_t (P_{it}^2)) sqrt(Σ_{t=1}^n w_t (P_{jt}^2))) (6)
Naturally, larger weights are assigned to recent PnL values (w_t > w_{t+1}, t=1,...,n). For example, w_t = 1 - t/n, which is inversely proportional to the time index t. The formula transforms input pairs of vectors (P_i, P_j) into time-scaled vectors and then computes the angle between the two scaled vectors:
P'_i = [sqrt(w_1)P_{i1}, sqrt(w_2)P_{i2}, ..., sqrt(w_n)P_{in}]^T ∈ R^n (7)
P'_j = [sqrt(w_1)P_{j1}, sqrt(w_2)P_{j2}, ..., sqrt(w_n)P_{jn}]^T ∈ R^n
As a result, the temporal-based correlation still preserves many desirable aspects of the traditional dot product, such as commutative, distributive, and bilinear properties.
The Pearson correlation coefficient can be computed here for the two scaled vectors in Equation 7. We can see that the centered variables have zero correlation or are uncorrelated in the sense of the Pearson correlation coefficient (i.e. the mean of each vector is subtracted from the elements of that vector), while orthogonality is a property of the raw variables. Zero correlation implies that the two demeaned vectors are orthogonal. The demeaning process often changes the angle of each vector and the angle between two vectors. Therefore, two vectors could be uncorrelated but not orthogonal, and vice versa. For further information about linear independent, orthogonal, and uncorrelated variables, see Joseph Rodgers et al. (1984).
Generalized Correlation
Data transformation can be an important tool for proper data analysis. There are two kinds of transformations: linear and nonlinear. A linear transformation (such as multiplication or addition of a constant) preserves the linear relationships among the variables, so it does not change the correlation among the variables. Below we will consider nonlinear transformations, which typically modify the correlation between two variables.
The two correlation formulas above compute correlation coefficients using daily PnL values. The generalized correlation creates a matrix M^{k×n}, then transforms the two PnL vectors to a different Euclidean space:
Q_i = M^{k×n}P_i ∈ R^k (8)
Q_j = M^{k×n}P_j ∈ R^k
The regular correlation now is computed in the transformed domain, with some additional features added by the transformed matrix M^{k×n}. If M^{k×n} = I^{n×n} is the identity matrix, we obtain the regular correlation scheme. Here we take a look at some other particularly useful transformations.
The weekly PnL correlation is computed for weekly instead of daily PnL vectors. In this case, k = ⌊n/5⌋ and the transformation matrix becomes
M^{k×n} = [m_{i,j}]_{\lfloor n/5 \rfloor × n} (9)
where m_{i,(i-1)*5+t} = 1/5 (i ∈ [1, ⌊n/5⌋] and t ∈ [1, 5]) and all other elements are zero. The weekly correlation is usually higher than daily values, but it is another way to understand alphas. The monthly PnL correlation is computed using a similar approach.
The temporal-based correlation is another form of generalized correlation, corresponding to the square diagonal transformation matrix:
M^{n×n} = [m_{i,j}]_{n×n} (10)
where m_{i,j} = sqrt(w_i) if i = j, m_{i,j} = 0 otherwise. Under this transformation, the input PnL vectors are transformed into time-scaled vectors, as in Equation 7.
The sign PnL correlation is another form of PnL vector correlation, in which the correlation is computed over the signs of the PnL values instead of the values themselves. The transformation matrix now is a data-dependent diagonal matrix and its element values depend on input PnL vectors. As a result, the input pairs (P_i, P_j) are transformed into the following form:
Q'_i = [sgn(P_{i1}), sgn(P_{i2}), ..., sgn(P_{in})]^T ∈ R^n (11)
Q'_j = [sgn(P_{j1}), sgn(P_{j2}), ..., sgn(P_{jn})]^T ∈ R^n
where sgn(x) is the sign (or signum) function and takes the values (1, 0, -1), corresponding to (positive, zero, negative) values of x.
ALPHA VALUE CORRELATION
Denote the alpha position vector on the t^{th} day by
α_i^{(t)} = [α_{i1}^{(t)}, α_{i2}^{(t)}, ..., α_{im}^{(t)}]^T ∈ R^m (12)
where m is the number of instruments, α_{ik}^{(t)} (≤ k ≤ m) is (or is proportional to) the amount of money invested in k^{th} instrument, and Σ_{k=1}^m α_{ik}^{(t)} is (or is proportional to) the total amount of money invested in the portfolio. It is sometimes useful to consider the alpha position vectors as well as the PnL vectors. In particular, portfolio managers often consider two correlation measures based on positions: the position correlation and the trading correlation.
The position correlation between two alphas over a period of d days is computed by forming the following two vectors:
α_i = [α_i^{(1)}, α_i^{(2)}, ..., α_i^{(d)}]^T ∈ R^{m*d} (13)
α_j = [α_j^{(1)}, α_j^{(2)}, ..., α_j^{(d)}]^T ∈ R^{m*d}
The trading correlation between two alphas over a period of d days is computed by forming the two difference vectors:
α_i = [α_i^{(1)}-α_i^{(0)}, α_i^{(2)}-α_i^{(1)}, ..., α_i^{(d)}-α_i^{(d-1)}]^T ∈ R^{m*d} (14)
α_j = [α_j^{(1)}-α_j^{(0)}, α_j^{(2)}-α_j^{(1)}, ..., α_j^{(d)}-α_j^{(d-1)}]^T ∈ R^{m*d}
Normally, it is enough to take d = 20 days, so the alpha vector is of dimension 20 * the number of instruments in the universe. If two alphas take positions on different universes of instruments, the intersection of the two universes is used for the calculations.
CORRELATION WITH ALPHA POOL
The above correlation methods are used for checking the correlation between two individual alphas. Naturally, given a pool of alphas, the maximum correlation has been used as a measure of the value added by a given alpha. As the number of alphas increases, the average correlation becomes more important than a single max correlation.
T-corr is defined as the sum of the correlations of the given alpha with all other alphas. The average correlation and T-corr provide additional powerful measures of alpha value addition, along with the max correlation.
A correlation density distribution is more important than a singular maximum value or even the average correlation value. Table 8.1 shows a sample histogram of correlation density (20 bins of size 0.1). Numerous features can be extracted from the histogram in addition to the maximum correlation and the average correlation. For example, the scaled average score of one alpha with the pool could be defined as Σ_{j=-10}^9 c_j * j/10 (c_j is taken from Table 8.1). The score ranges in [-1, 1], which increases if the number of alphas with positive correlation increases or the number of alphas with negative correlation decreases.
Table 8.1 A histogram of correlation
Bin scnt(%) count_in_number
0.9 c9 0
0.8 c8 0
0.7 c7 0
0.6 c6 0
0.5 c5 0
0.4 c4 167
0.3 c3 5,102
0.2 c2 70,294
0.1 c1 283,436
0 c0 438,720
-0.1 c_1 286,478
-0.2 c_2 36,889
-0.3 c_3 1,293
-0.4 c_4 59
-0.5 c_5 0
-0.6 c_6 0
-0.7 c_7 0
-0.8 c_8 0
-0.9 c_9 0
-1 c_10 0
CONCLUSION
We have surveyed several different approaches to evaluating the correlations between the PnLs and positions of alphas and pools of alphas. There are, of course, more statistical and less algebraic approaches to evaluate correlation, such as Spearman's rank correlation and the Kendall rank correlation. Within the scope of this chapter, we have covered only some of the most common methods for evaluating alpha correlation. PnL correlation can be evaluated over a longer period of time (2–4 years or longer) in comparison with alpha value correlation (which requires a short, recent period of time) because of the limitations of computational resources.
One reasonable idea can often be used to develop numerous alphas, depending on different techniques and datasets. Because they are developed using a single idea, these alphas have a tendency to be highly correlated. Sometimes there are instances when it is beneficial to combine some or all of these highly correlated alphas instead of selecting only one alpha and removing all others. Two alphas may have highly correlated historical performance, but the future is uncertain and it is not always clear which one may add more value in the future. Therefore, in terms of resource allocation for two high-correlation alphas (e.g. A and B), one can divide resources (not necessarily equally) between A and B instead of allocating all of the resources to a single alpha. A single alpha cannot fully describe every aspect of one idea, but each alpha represents that idea in a different way; hence, using all these alphas at once may provide a more complete view of the idea and make the overall strategy more robust.
The ultimate objective of alpha correlation is to find the true value of adding one new alpha, given a pool of existing alphas, which becomes increasingly important as the number of alphas grows toward the sky. Using multiple correlation approaches leads to a better understanding of the alpha signals in recent history as well as over a longer past period. An alpha based on a completely novel trading idea is generally unique and adds the most value to the alpha pool.
