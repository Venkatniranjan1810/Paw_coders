import yfinance as yf
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.rolling import RollingOLS
from pandas_datareader.data import FamaFrenchReader
import warnings
warnings.filterwarnings("ignore")

def get_yahoo_monthly_returns(ticker, start_date, end_date):
    """Downloads daily prices, handles yfinance's MultiIndex, resamples to monthly returns, and normalizes the index."""
    df = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    monthly_prices = df['Close'].resample('ME').last()
    returns = monthly_prices.pct_change().dropna()
    returns.index = returns.index.to_period('M').to_timestamp('M')
    returns.name = 'Asset_Return'
    return returns

def get_french_factors(start_date, end_date):
    """Downloads FF3, FF5, and Momentum factors, merges them, and normalizes the PeriodIndex."""
    ff3 = FamaFrenchReader("F-F_Research_Data_Factors", start=start_date, end=end_date).read()[0]
    ff5 = FamaFrenchReader("F-F_Research_Data_5_Factors_2x3", start=start_date, end=end_date).read()[0]
    mom = FamaFrenchReader("F-F_Momentum_Factor", start=start_date, end=end_date).read()[0]
    
    for df in [ff3, ff5, mom]:
        df.columns = df.columns.str.strip()
        df.iloc[:, :] = df.iloc[:, :] / 100.0
        
    factors = ff5.copy()
    factors['Mom'] = mom['Mom']
    factors['HML_FF3'] = ff3['HML']
    
    factors.index = factors.index.to_timestamp('M')
    return factors

def run_static_ols(y, X, model_name):
    """Runs a standard OLS regression and prints a formatted summary."""
    X = sm.add_constant(X)
    model = sm.OLS(y, X, missing='drop').fit()
    print(f"\n{'='*40}\n{model_name} REGRESSION SUMMARY\n{'='*40}")
    print(model.summary())
    return model

def run_rolling_ols(y, X, window=36):
    """Runs a rolling OLS to estimate time-varying factor betas (Advanced)."""
    X = sm.add_constant(X)
    rolling_model = RollingOLS(y, X, window=window, min_nobs=window).fit()
    print(f"\n{'='*40}\nROLLING OLS SUMMARY (Window: {window} Months)\n{'='*40}")
    print(f"Rolling Alpha Mean: {rolling_model.params['const'].mean():.4f}")
    print(f"Rolling Beta_MKT Mean: {rolling_model.params['Mkt-RF'].mean():.4f}")
    print(f"Rolling Beta_MKT Std Dev: {rolling_model.params['Mkt-RF'].std():.4f}")
    return rolling_model

if __name__ == "__main__":
    TICKER = "AAPL"
    START = "2010-01-01"
    END = "2026-6-1"
    
    print(f"Downloading data for {TICKER} via Yahoo Finance and Kenneth French's Data Library...")
    asset_returns = get_yahoo_monthly_returns(TICKER, START, END)
    factors = get_french_factors(START, END)
    
    df = pd.concat([asset_returns, factors], axis=1).dropna()
    df['Excess_Return'] = df['Asset_Return'] - df['RF']
    
    X_ff3 = df[['Mkt-RF', 'SMB', 'HML_FF3']]
    X_ff5 = df[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']]
    X_ff5_mom = df[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'Mom']]
    y = df['Excess_Return']
    
    run_static_ols(y, X_ff3, "FAMA-FRENCH 3-FACTOR")
    run_static_ols(y, X_ff5, "FAMA-FRENCH 5-FACTOR")
    run_static_ols(y, X_ff5_mom, "FAMA-FRENCH 5-FACTOR + MOMENTUM")
    
    rolling_results = run_rolling_ols(y, X_ff5_mom, window=36)
    
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(rolling_results.params.index, rolling_results.params['Mkt-RF'], color='black', linewidth=1.2)
        ax.fill_between(rolling_results.params.index, 
                        rolling_results.params['Mkt-RF'] - rolling_results.bse['Mkt-RF'],
                        rolling_results.params['Mkt-RF'] + rolling_results.bse['Mkt-RF'], 
                        color='gray', alpha=0.2, label='95% Confidence Interval')
        ax.axhline(y=1.0, color='red', linestyle='--', linewidth=0.8, label='Beta = 1.0')
        ax.set_title(f'Time-Varying Market Beta (36-Month Rolling Window) for {TICKER}')
        ax.set_ylabel('Beta')
        ax.legend()
        plt.tight_layout()
        plt.savefig(f'{TICKER}_rolling_beta.png')
        print(f"\nRolling Beta plot saved as {TICKER}_rolling_beta.png")
    except ImportError:
        pass
