# Chapter Five. Framework Overview

NOW YOU HAVE SOME THEORY AND PERHAPS A FEW quantitative tools at your disposal you are ready to begin creating trading systems. In part three of this book I am going to to describe a framework which will provide you with a template for the creation of almost any kind of strategy.

## Chapter overview

| A bad example | A trading system with some fatal flaws. |
| :--- | :--- |
| Why use a modular framework | The reasons why a modular framework makes sense for systematic trading strategies. |
| The elements of the framework | A brief road map of the various components in the framework. |

The following chapters in part three will describe each component in more detail. In the final part of the book I'll show three examples of how this framework can be used, for semi-automatic traders, asset allocating investors and staunch systems traders.

## A bad example
Here's an example of the kind of trading system you find in many books and websites.<sup>69</sup>

| Entry rule | Buy when the 20 day moving average rises over the 40 day, and vice versa. |
| :--- | :--- |
| Exit rule | Reverse when the entry rule is broken, so if you are long close when the 20 day moving average falls behind the 40 day and go short. |
| Position size | Never trade more than 10 Eurodollar futures, 1 FTSE contract or £10 per spread bet point. |
| Money management | Never bet more than 3% of your capital on each trade. |
| Stop loss | Set a trailing stop to close once you have lost 3% of your capital. If you find yourself triggering stops too frequently, then widen them. |

I am not going to discuss the entry or exit rule.<sup>70</sup> However the position sizing, money management and stop loss are a mess.
Firstly why 3%? Will this generate the right amount of risk? What if I'm particularly conservative, should I still use 3%? If I don't like a particular trade that much, what should I bet? I typically have 40 positions in my portfolio, so should I be putting 40 lots of 3% of my portfolio at risk at any one time (meaning 120% of my total portfolio is at risk)? Does 3% make sense if I am using a slower trading rule?
The position sizes above might make sense for someone with an account size of perhaps £50,000 and a certain risk appetite, but what about everyone else? They might be correct when the book was written, but are they still right when we read it five years later? What about an instrument that isn't listed, can we trade it? How?
Finally, setting a stop loss based solely on your capital and personal pain threshold is incorrect.<sup>71</sup> Someone with a tiny account who hated losing money would be triggering their very tight stops after a few minutes, whilst a large hedge fund might close a losing position after decades. Stops that would make sense in oil futures would be completely wrong in the relatively quiet USD/CAD FX market. A stop that was correct in the peaceful calm of 2006 would be absurdly tight in the insanity we saw in 2008.
The solution is to separate out the components of your system: trading rules (including explicit or implicit stop losses), position sizing, and the calculation of your volatility target (the average amount of cash you are willing to risk). You can then design each component independently of the other moving parts.
Trading rules and stop losses should be based only on expected market price volatility, and should never take your account size into consideration. Calculating a volatility target, how much of your capital to put at risk, is a function of account size and your pain threshold.<sup>72</sup> Positions should then be sized based on how volatile markets are, how confident your price forecasts are, and the amount of capital you wish to gamble.
Each of these components is part of the modular framework which together form a complete trading system.

## Why a modular framework?
Remember that I drew an analogy between cars and trading systems in the introduction of this book. Trading rules are the engine of the system. These give you a forecast for instrument prices; whether they are expected to go up or down and by how much. In a car the chassis, drive train and gearbox translate the power the engine is producing into forward movement. Similarly, you will have a position risk management framework wrapped around your trading rules. This translates forecasts into the actual positions you need to hold.
As I said in the introduction the components of a modern car are modular, so they can be individually substituted for alternatives. The trading rules and other components in my framework can also be swapped and changed.
The words module and component could imply that these are complex processes which need thousands of lines of computer code to implement. This is not the case. Every part involves just a few steps of basic arithmetic which require just a calculator or simple spreadsheet.
Let's look in more detail at the advantages of the modular approach.

### Flexibility
The most obvious benefit of a modular design is flexibility. Cars really can be any colour you like, including black. Similarly, my framework can be adapted for almost any trading rule, including the discretionary forecasts used by semi-automatic traders and the very simple rule used by asset allocating investors. If you don't like the position sizing component, or any other part of the framework, you can replace it with your own.

### Transparent modules
It's possible to have frameworks that are nicely modular but which contain entirely opaque black boxes. Most PCs are built like this. You can replace the hard disc or graphics card, but you can't easily modify them or make your own, so you are stuck with substituting one mysterious part with another.
In contrast each component in my framework is transparent — I'll explain how and why it is constructed. This should give you the understanding and confidence to adapt each module, or create your own from scratch.

### Individual components with well defined interface
If you replace the gearbox in your car you need to be sure that the car will still go forward or backwards as required. But if the drive shaft output is reversed on your new gearbox you will end up driving into your front door when you wanted to reverse out of your driveway. To avoid this we need to specify that the shaft on the gearbox must rotate clockwise to make the car go forward, and vice versa.
Similarly if you use a new trading rule then the rest of the modular trading system framework should still work correctly and give you appropriately sized positions. To do this the individual components need to have a well defined interface — a specification describing how they interact with other parts of the system.
For example in the framework it will be important that a trading rule forecast of say +1.5 has a consistent meaning, no matter what style of trading or instrument you are using.<sup>73</sup>

### Getting the boring bit right
The part of the trading system wrapped around the trading rules, the framework, is something that's easily ignored. Creating it is a boring task compared with developing new and exciting trading rules, or making your own discretionary forecasts. But it's incredibly important. By creating a standard framework I've done this dull but vital work for you.
The framework will work correctly for any trading rule that produces forecasts in a consistent way with the right interface. So it won't need to be radically redesigned for any new rules. Also by using the framework asset allocating investors and semi-automatic traders can get much of the benefits of systematic trading without using trading rules to forecast prices.

### Examples give you a starting point
Creating a new trading system from scratch is quite a daunting prospect. In the final part of this book there are three detailed examples showing how the framework can be used to suit asset allocating investors, semi-automatic traders and staunch systematic traders. Together these provide a set of systems you can use as a starting point for developing your own ideas.

## The elements of the framework
Table 15 shows the components you'd have in a small trading system with two trading rules, a total of four trading rule variations, and two instruments. You first create a trading subsystem for each instrument. Each subsystem tries to predict the price of an individual instrument, and calculate the appropriate position required. These subsystems are then combined into a portfolio, which forms the final trading system.

**TABLE 15: EXAMPLE OF COMPONENTS IN A TRADING SYSTEM**
*This trading system has two trading rules A and B; three rule variations A1, A2 and B1; and two instruments X and Y. Dotted lines show trading subsystems for X and Y.*

### Instruments to trade
Instruments are the things you trade and hold positions in. They could be any financial asset including directly held instruments such as equities and bonds, or derivatives like options, futures, contracts for difference and spread bets. You can also trade collective funds such as exchange traded funds (ETFs), mutual funds, and even hedge funds.

### Forecasts
A forecast is an estimate of how much a particular instrument's price will change, given a particular trading rule variation. For example a simple equities strategy might have three forecasts: two variations on a trend following rule, each looking for different speeds of trend, and a separate equity value trading rule with a single variation. If you are trading two instruments as in table 15 then there will be a total of 3 × 2 = 6 forecasts to make.
The trading rules which produce forecasts are the engine at the heart of all trading systems used by staunch systems traders. The biggest difference between strategies will be in which rules and variations are used, and which instruments are traded. In comparison the rest of the framework will be fairly similar.
Semi-automatic traders make discretionary forecasts, rather than using systematic rules. Asset allocating investors don't try and predict asset prices and use a single fixed forecast for all instruments.

### Combined forecasts
You need a single forecast of whether an instrument will go up or down in price, and by how much. If you have more than one forecast you will need to combine them into one combined forecast per instrument, using a weighted average. To do this you'll allocate forecast weights to each trading rule variation.

### Volatility targeting
It's important to be precise about how much overall risk you want to take in your trading system. I define this as the typical average daily loss you are willing to expose yourself to. This volatility target is determined using your wealth, tolerance for risk, access to leverage and expected profitability. Initially we'll assume that you're putting all of your capital into a single trading subsystem, for just one instrument.

### Scaled positions
You can now decide how much of the underlying asset to hold based on how risky your instruments are, how confident you are about your forecasts, and your volatility target. The positions you will calculate assume for now that you're just trading one isolated instrument, in a single trading subsystem.
At this point you've effectively got a complete trading system, but for a single instrument. Just as the cells in the human body are each individual living organisms, these trading subsystems are self-contained units, but in the next stage you'll be putting them together.

### Portfolios
To get maximum diversification you'd usually want to trade multiple instruments and put together a portfolio of trading subsystems, each responsible for a single instrument. This requires determining how you are going to allocate capital to the different subsystems in your portfolio, which you will do using instrument weights. After applying this stage you'll end up with portfolio weighted positions in each instrument, which are then used to calculate the trades you need to do.

### Speed and Size
This isn't a separate component in the framework, but a set of principles which apply to the entire system. When designing trading systems it's important to know how expensive they are to trade, and whether you have an unusually large or small amount of capital. Given that information, how should you then tailor your system? I'll address both of these issues in detail in the final chapter of part three.

---
69. This is a hypothetical example and as far as I know isn't identical to any publicly available system.
70. The rules aren't too bad, as they are purely systematic and very simple. However they are binary (you're either fully in or out) which isn't ideal, and having only one trading rule variation is also less than perfect.
71. This is recognised by most good traders. Here is Jack Schwager, in *Hedge Fund Wizards*, interviewing hedge fund manager Colm O'Shea: Jack: "So you don't use stops?" Colm: "No I do. I just set them wide enough. In those early days I wasn't setting stops at levels that made sense on the underlying hypothesis of the trade. I was setting stops *based on my pain threshold*. When I get out of a trade now it is because I was wrong. ... Prices are *inconsistent with my hypothesis*. I'm wrong and I need to get out and rethink the situation." (My emphasis.)
72. There are other considerations, such as the amount of leverage required versus what is available, and the expected performance of the system. I'll discuss these in more detail in chapter nine, 'Volatility targeting'.
73. It will become clear in later chapters what this consistent meaning is.
