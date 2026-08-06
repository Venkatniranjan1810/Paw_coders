"""
Fama-French Factor Analysis Tool
=================================
Performs FF3, FF5, FF5+Momentum regressions and advanced analysis
Data Sources: Yahoo Finance (stock data), Kenneth French Data Library (factors)
"""

import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
import numpy as np
import pandas as pd
import yfinance as yf
import pandas_datareader.data as web
import statsmodels.api as sm
from statsmodels.regression.rolling import RollingOLS
from statsmodels.stats.diagnostic import het_white, acorr_ljungbox
from statsmodels.stats.stattools import jarque_bera
from arch import arch_model
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from scipy import stats
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import io

# Set style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

# =============================================================================
# SECTION 2: DATA FETCHING FUNCTIONS
# =============================================================================

def get_fama_french_factors(start_date, end_date, factor_set='F-F_Research_Data_5_Factors_2x3'):
    """
    Download Fama-French factors from Kenneth French's data library.
    
    Parameters:
    -----------
    start_date : str
        Start date in 'YYYY-MM-DD' format
    end_date : str  
        End date in 'YYYY-MM-DD' format
    factor_set : str
        Which factor dataset to download
        
    Returns:
    --------
    pd.DataFrame
        DataFrame with factor returns
    """
    try:
        # Try pandas_datareader first
        factors = web.DataReader(factor_set, 'famafrench', start_date, end_date)[0]
        return factors
    except Exception as e1:
        print(f"pandas_datareader failed: {e1}")
        print("Attempting direct download from French data library...")
        
        try:
            # Direct download approach
            url = f"https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{factor_set}_CSV.zip"
            response = requests.get(url, timeout=30)
            
            # Parse the CSV from zip
            import zipfile
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for name in z.namelist():
                    if name.endswith('.CSV'):
                        with z.open(name) as f:
                            lines = [l.decode('utf-8') for l in f.readlines()]
            
            # Parse the data
            data_lines = []
            start_parsing = False
            for line in lines:
                if line.strip().startswith('19'):
                    start_parsing = True
                if start_parsing and line.strip():
                    data_lines.append(line.strip())
            
            # Create DataFrame
            from io import StringIO
            df = pd.read_csv(StringIO('\n'.join(data_lines)), header=None)
            
            # Set column names based on factor set
            if '5_Factors' in factor_set:
                df.columns = ['Date', 'Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'RF']
            elif '3_Factors' in factor_set:
                df.columns = ['Date', 'Mkt-RF', 'SMB', 'HML', 'RF']
            
            df['Date'] = pd.to_datetime(df['Date'], format='%Y%m')
            df.set_index('Date', inplace=True)
            df = df.astype(float) / 100  # Convert percentages to decimals
            
            # Filter by date
            df = df.loc[start_date:end_date]
            return df
            
        except Exception as e2:
            print(f"Direct download also failed: {e2}")
            print("Using synthetic factor data for demonstration...")
            return generate_synthetic_factors(start_date, end_date)


def get_momentum_factor(start_date, end_date):
    """
    Download Fama-French Momentum factor (UMD).
    """
    try:
        mom = web.DataReader('F-F_Momentum_Factor', 'famafrench', start_date, end_date)[0]
        return mom
    except Exception as e:
        print(f"Momentum factor download failed: {e}")
        print("Using synthetic momentum factor...")
        return generate_synthetic_momentum(start_date, end_date)


def get_stock_data(ticker, start_date, end_date):
    """
    Download stock data from Yahoo Finance and calculate monthly returns.
    
    Parameters:
    -----------
    ticker : str
        Stock ticker symbol
    start_date : str
        Start date in 'YYYY-MM-DD' format
    end_date : str
        End date in 'YYYY-MM-DD' format
        
    Returns:
    --------
    pd.DataFrame
        DataFrame with monthly returns and excess returns
    """
    print(f"Downloading data for {ticker}...")
    stock = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if stock.empty:
        raise ValueError(f"No data found for {ticker}")

    # Resample to monthly and calculate returns
    # yfinance >= 0.2.36 removed 'Adj Close', 'Close' is now auto-adjusted
    price_col = 'Adj Close' if 'Adj Close' in stock.columns else 'Close'
    stock_monthly = stock[price_col].resample('ME').last() # Note: 'M' is deprecated, use 'ME'
    returns = stock_monthly.pct_change().dropna()
    returns.name = 'Return'
    
    return pd.DataFrame(returns)


def generate_synthetic_factors(start_date, end_date):
    """Generate synthetic Fama-French 5 factors for demonstration."""
    dates = pd.date_range(start_date, end_date, freq='M')
    np.random.seed(42)
    n = len(dates)
    
    # Generate correlated factors with realistic properties
    cov_matrix = np.array([
        [0.0025, 0.0005, 0.0003, 0.0002, 0.0001, 0.0001],
        [0.0005, 0.0010, 0.0002, 0.0001, 0.0001, 0.0000],
        [0.0003, 0.0002, 0.0008, 0.0001, 0.0000, 0.0000],
        [0.0002, 0.0001, 0.0001, 0.0006, 0.0001, 0.0000],
        [0.0001, 0.0001, 0.0000, 0.0001, 0.0005, 0.0000],
        [0.0001, 0.0000, 0.0000, 0.0000, 0.0000, 0.0002]
    ])
    
    means = [0.005, 0.002, 0.002, 0.002, 0.001, 0.002]
    factors = np.random.multivariate_normal(means, cov_matrix, n)
    
    df = pd.DataFrame(factors, index=dates, 
                      columns=['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'RF'])
    return df


def generate_synthetic_momentum(start_date, end_date):
    """Generate synthetic momentum factor."""
    dates = pd.date_range(start_date, end_date, freq='M')
    np.random.seed(43)
    n = len(dates)
    
    mom = np.random.normal(0.003, 0.02, n)
    return pd.DataFrame(mom, index=dates, columns=['Mom'])


# =============================================================================
# SECTION 3: REGRESSION ANALYSIS FUNCTIONS
# =============================================================================

def run_ff3_regression(excess_returns, factors):
    """
    Run Fama-French 3-Factor Model Regression.
    
    Model: R_it - RF_t = α + β_MKT*(MKT-RF)_t + β_SMB*SMB_t + β_HML*HML_t + ε_t
    
    Parameters:
    -----------
    excess_returns : pd.Series
        Excess returns of the asset
    factors : pd.DataFrame
        DataFrame containing Mkt-RF, SMB, HML, RF columns
        
    Returns:
    --------
    dict
        Regression results and diagnostics
    """
    print("\n" + "="*70)
    print("FAMA-FRENCH 3-FACTOR MODEL REGRESSION")
    print("="*70)
    
    # Prepare data
    y = excess_returns
    X = factors[['Mkt-RF', 'SMB', 'HML']]
    X = sm.add_constant(X)
    
    # Run regression
    model = sm.OLS(y, X, missing='drop').fit()
    
    # Diagnostics
    diagnostics = calculate_diagnostics(model, X, y)
    
    # Print results
    print(model.summary())
    print_diagnostics(diagnostics, "FF3")
    
    # Interpretation
    print("\n--- INTERPRETATION ---")
    print(f"• Market Beta (β_MKT): {model.params['Mkt-RF']:.4f} - ", end="")
    if model.params['Mkt-RF'] > 1:
        print("Stock is more volatile than market (aggressive)")
    elif model.params['Mkt-RF'] < 1:
        print("Stock is less volatile than market (defensive)")
    else:
        print("Stock moves with the market")
    
    print(f"• Size Factor (β_SMB): {model.params['SMB']:.4f} - ", end="")
    if model.params['SMB'] > 0.2:
        print("Small-cap tilt (positive exposure to small firms)")
    elif model.params['SMB'] < -0.2:
        print("Large-cap tilt (negative exposure to small firms)")
    else:
        print("Neutral size exposure")
    
    print(f"• Value Factor (β_HML): {model.params['HML']:.4f} - ", end="")
    if model.params['HML'] > 0.2:
        print("Value tilt (positive exposure to value stocks)")
    elif model.params['HML'] < -0.2:
        print("Growth tilt (negative exposure to value stocks)")
    else:
        print("Neutral value/growth exposure")
    
    print(f"• Alpha (α): {model.params['const']:.4f} per month = {model.params['const']*12*100:.2f}% annualized")
    print(f"• Alpha t-stat: {model.tvalues['const']:.2f} (significant if |t| > 2)")
    print(f"• R²: {model.rsquared:.4f} ({model.rsquared*100:.1f}% of variation explained)")
    
    return {
        'model_name': 'FF3',
        'model': model,
        'params': model.params,
        'tvalues': model.tvalues,
        'pvalues': model.pvalues,
        'rsquared': model.rsquared,
        'adj_rsquared': model.rsquared_adj,
        'diagnostics': diagnostics,
        'n_obs': model.nobs
    }


def run_ff5_regression(excess_returns, factors):
    """
    Run Fama-French 5-Factor Model Regression.
    
    Model: R_it - RF_t = α + β_MKT*(MKT-RF)_t + β_SMB*SMB_t + β_HML*HML_t 
                       + β_RMW*RMW_t + β_CMA*CMA_t + ε_t
    """
    print("\n" + "="*70)
    print("FAMA-FRENCH 5-FACTOR MODEL REGRESSION")
    print("="*70)
    
    # Prepare data
    y = excess_returns
    X = factors[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']]
    X = sm.add_constant(X)
    
    # Run regression
    model = sm.OLS(y, X, missing='drop').fit()
    
    # Diagnostics
    diagnostics = calculate_diagnostics(model, X, y)
    
    # Print results
    print(model.summary())
    print_diagnostics(diagnostics, "FF5")
    
    # Interpretation
    print("\n--- INTERPRETATION ---")
    print(f"• Market Beta (β_MKT): {model.params['Mkt-RF']:.4f}")
    print(f"• Size Factor (β_SMB): {model.params['SMB']:.4f}")
    print(f"• Value Factor (β_HML): {model.params['HML']:.4f}")
    print(f"• Profitability Factor (β_RMW): {model.params['RMW']:.4f} - ", end="")
    if model.params['RMW'] > 0.2:
        print("Exposure to profitable firms (quality tilt)")
    elif model.params['RMW'] < -0.2:
        print("Exposure to unprofitable firms")
    else:
        print("Neutral profitability exposure")
    
    print(f"• Investment Factor (β_CMA): {model.params['CMA']:.4f} - ", end="")
    if model.params['CMA'] > 0.2:
        print("Conservative investment tilt (low asset growth)")
    elif model.params['CMA'] < -0.2:
        print("Aggressive investment tilt (high asset growth)")
    else:
        print("Neutral investment exposure")
    
    print(f"• Alpha (α): {model.params['const']*12*100:.2f}% annualized")
    print(f"• R²: {model.rsquared:.4f} (vs FF3 R²: compare improvement)")
    
    return {
        'model_name': 'FF5',
        'model': model,
        'params': model.params,
        'tvalues': model.tvalues,
        'pvalues': model.pvalues,
        'rsquared': model.rsquared,
        'adj_rsquared': model.rsquared_adj,
        'diagnostics': diagnostics,
        'n_obs': model.nobs
    }


def run_ff5_mom_regression(excess_returns, factors, momentum):
    """
    Run Fama-French 5-Factor + Momentum (Carhart 4-Factor extended) Regression.
    
    Model: R_it - RF_t = α + β_MKT*(MKT-RF)_t + β_SMB*SMB_t + β_HML*HML_t 
                       + β_RMW*RMW_t + β_CMA*CMA_t + β_MOM*MOM_t + ε_t
    """
    print("\n" + "="*70)
    print("FAMA-FRENCH 5-FACTOR + MOMENTUM MODEL REGRESSION")
    print("="*70)
    
    # Prepare data
    y = excess_returns
    X = factors[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']].copy()
    X['Mom'] = momentum['Mom']
    X = sm.add_constant(X)
    
    # Run regression
    model = sm.OLS(y, X, missing='drop').fit()
    
    # Diagnostics
    diagnostics = calculate_diagnostics(model, X, y)
    
    # Print results
    print(model.summary())
    print_diagnostics(diagnostics, "FF5+Mom")
    
    # Interpretation
    print("\n--- INTERPRETATION ---")
    print(f"• Momentum Factor (β_MOM): {model.params['Mom']:.4f} - ", end="")
    if model.params['Mom'] > 0.2:
        print("Momentum stock (tends to continue recent trends)")
    elif model.params['Mom'] < -0.2:
        print("Contrarian/reversal stock (tends to reverse recent trends)")
    else:
        print("Neutral momentum exposure")
    
    print(f"• Alpha (α): {model.params['const']*12*100:.2f}% annualized")
    print(f"• R²: {model.rsquared:.4f} (vs FF5 R²: check momentum contribution)")
    
    # Check if momentum is significant
    if model.pvalues['Mom'] < 0.05:
        print("• ✅ Momentum factor is STATISTICALLY SIGNIFICANT (p < 0.05)")
    else:
        print("• ❌ Momentum factor is NOT statistically significant")
    
    return {
        'model_name': 'FF5+Mom',
        'model': model,
        'params': model.params,
        'tvalues': model.tvalues,
        'pvalues': model.pvalues,
        'rsquared': model.rsquared,
        'adj_rsquared': model.rsquared_adj,
        'diagnostics': diagnostics,
        'n_obs': model.nobs
    }


# =============================================================================
# SECTION 4: DIAGNOSTICS FUNCTIONS
# =============================================================================

def calculate_diagnostics(model, X, y):
    """
    Calculate comprehensive regression diagnostics.
    """
    residuals = model.resid
    fitted = model.fittedvalues
    
    # 1. White's test for heteroskedasticity
    try:
        white_test = het_white(residuals, X)
        white_stat, white_pvalue = white_test[0], white_test[1]
    except:
        white_stat, white_pvalue = np.nan, np.nan
    
    # 2. Ljung-Box test for autocorrelation
    try:
        lb_test = acorr_ljungbox(residuals, lags=[10], return_df=True)
        lb_stat, lb_pvalue = lb_test.iloc[0]['lb_stat'], lb_test.iloc[0]['lb_pvalue']
    except:
        lb_stat, lb_pvalue = np.nan, np.nan
    
    # 3. Jarque-Bera test for normality
    try:
        jb_stat, jb_pvalue = jarque_bera(residuals)
    except:
        jb_stat, jb_pvalue = np.nan, np.nan
    
    # 4. Durbin-Watson statistic
    from statsmodels.stats.stattools import durbin_watson
    dw_stat = durbin_watson(residuals)
    
    # 5. Information Criteria
    aic = model.aic
    bic = model.bic
    
    # 6. Residual statistics
    residual_stats = {
        'mean': residuals.mean(),
        'std': residuals.std(),
        'skew': residuals.skew(),
        'kurtosis': residuals.kurtosis(),
        'min': residuals.min(),
        'max': residuals.max()
    }
    
    return {
        'white_test': {'stat': white_stat, 'pvalue': white_pvalue},
        'ljung_box': {'stat': lb_stat, 'pvalue': lb_pvalue},
        'jarque_bera': {'stat': jb_stat, 'pvalue': jb_pvalue},
        'durbin_watson': dw_stat,
        'aic': aic,
        'bic': bic,
        'residual_stats': residual_stats
    }


def print_diagnostics(diagnostics, model_name):
    """Print formatted diagnostics."""
    print(f"\n{'='*50}")
    print(f"DIAGNOSTICS - {model_name}")
    print(f"{'='*50}")
    
    print(f"\n1. HETEROSKEDASTICITY (White's Test):")
    print(f"   Statistic: {diagnostics['white_test']['stat']:.4f}")
    print(f"   P-value: {diagnostics['white_test']['pvalue']:.4f}")
    if diagnostics['white_test']['pvalue'] < 0.05:
        print("   ⚠️  Heteroskedasticity detected - consider robust standard errors")
    else:
        print("   ✅ No significant heteroskedasticity")
    
    print(f"\n2. AUTOCORRELATION (Ljung-Box Test):")
    print(f"   Statistic: {diagnostics['ljung_box']['stat']:.4f}")
    print(f"   P-value: {diagnostics['ljung_box']['pvalue']:.4f}")
    if diagnostics['ljung_box']['pvalue'] < 0.05:
        print("   ⚠️  Autocorrelation detected - consider Newey-West standard errors")
    else:
        print("   ✅ No significant autocorrelation")
    
    print(f"\n3. NORMALITY (Jarque-Bera Test):")
    print(f"   Statistic: {diagnostics['jarque_bera']['stat']:.4f}")
    print(f"   P-value: {diagnostics['jarque_bera']['pvalue']:.4f}")
    if diagnostics['jarque_bera']['pvalue'] < 0.05:
        print("   ⚠️  Residuals not normally distributed")
    else:
        print("   ✅ Residuals approximately normal")
    
    print(f"\n4. DURBIN-WATSON STATISTIC: {diagnostics['durbin_watson']:.4f}")
    print("   (Values near 2 indicate no autocorrelation; <1.5 or >2.5 are concerning)")
    
    print(f"\n5. INFORMATION CRITERIA:")
    print(f"   AIC: {diagnostics['aic']:.4f}")
    print(f"   BIC: {diagnostics['bic']:.4f}")
    
    print(f"\n6. RESIDUAL STATISTICS:")
    rs = diagnostics['residual_stats']
    print(f"   Mean: {rs['mean']:.6f} (should be ≈0)")
    print(f"   Std Dev: {rs['std']:.6f}")
    print(f"   Skewness: {rs['skew']:.4f} (should be ≈0)")
    print(f"   Kurtosis: {rs['kurtosis']:.4f} (normal=3)")


# =============================================================================
# SECTION 5: ADVANCED ANALYSIS FUNCTIONS
# =============================================================================

def run_rolling_regression(excess_returns, factors, momentum, window=36):
    """
    Run rolling window regression to analyze time-varying factor exposures.
    
    Parameters:
    -----------
    window : int
        Rolling window size in months (default: 36 months = 3 years)
    """
    print("\n" + "="*70)
    print("ADVANCED ANALYSIS 1: ROLLING REGRESSION (Time-Varying Factor Exposures)")
    print("="*70)
    print(f"Window Size: {window} months ({window/12:.1f} years)")
    
    # Prepare data with all 6 factors
    y = excess_returns
    X = factors[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']].copy()
    X['Mom'] = momentum['Mom']
    X = sm.add_constant(X)
    
    # Align data
    data = pd.concat([y, X], axis=1).dropna()
    y_aligned = data.iloc[:, 0]
    X_aligned = data.iloc[:, 1:]
    
    # Run Rolling OLS
    rolling_model = RollingOLS(y_aligned, X_aligned, window=window)
    rolling_results = rolling_model.fit()
    
    # Extract rolling coefficients
    rolling_params = rolling_results.params
    
    print(f"\nRolling Regression completed with {len(rolling_params)} windows")
    print("\n--- ROLLING BETA STATISTICS ---")
    
    factor_cols = ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'Mom']
    for col in factor_cols:
        if col in rolling_params.columns:
            print(f"\n{col}:")
            print(f"  Mean: {rolling_params[col].mean():.4f}")
            print(f"  Std:  {rolling_params[col].std():.4f}")
            print(f"  Min:  {rolling_params[col].min():.4f}")
            print(f"  Max:  {rolling_params[col].max():.4f}")
            print(f"  Range: {rolling_params[col].max() - rolling_params[col].min():.4f}")
    
    return {
        'rolling_params': rolling_params,
        'rolling_r2': rolling_results.rsquared,
        'window': window
    }


def run_garch_analysis(excess_returns):
    """
    Run GARCH(1,1) volatility modeling on residuals.
    """
    print("\n" + "="*70)
    print("ADVANCED ANALYSIS 2: GARCH(1,1) VOLATILITY MODELING")
    print("="*70)
    
    # Scale returns for numerical stability
    returns_scaled = excess_returns * 100
    
    try:
        # Fit GARCH(1,1)
        garch = arch_model(returns_scaled, vol='Garch', p=1, q=1, 
                          mean='Zero', dist='normal')
        garch_result = garch.fit(disp='off', show_warning=False)
        
        print("\nGARCH(1,1) Model Results:")
        print("-" * 40)
        print(f"ω (omega - long-run variance): {garch_result.params['omega']:.4f}")
        print(f"α (alpha - shock impact):     {garch_result.params['alpha[1]']:.4f}")
        print(f"β (beta - persistence):       {garch_result.params['beta[1]']:.4f}")
        
        # Persistence (α + β)
        persistence = garch_result.params['alpha[1]'] + garch_result.params['beta[1]']
        print(f"\nPersistence (α + β): {persistence:.4f}")
        if persistence > 0.9:
            print("  → High persistence - volatility shocks have long-lasting effects")
        elif persistence > 0.7:
            print("  → Moderate persistence - volatility shocks decay gradually")
        else:
            print("  → Low persistence - volatility reverts quickly to mean")
        
        # Half-life of volatility shocks
        if persistence < 1:
            half_life = np.log(0.5) / np.log(persistence)
            print(f"  → Half-life of volatility shocks: {half_life:.2f} months")
        
        # Get conditional volatility
        conditional_vol = garch_result.conditional_volatility / 100  # Scale back
        
        return {
            'garch_result': garch_result,
            'conditional_volatility': conditional_vol,
            'persistence': persistence,
            'params': garch_result.params
        }
        
    except Exception as e:
        print(f"GARCH estimation failed: {e}")
        return None


def run_bootstrap_regression(excess_returns, factors, momentum, n_bootstrap=1000):
    """
    Run bootstrap regression to get robust confidence intervals.
    """
    print("\n" + "="*70)
    print("ADVANCED ANALYSIS 3: BOOTSTRAP CONFIDENCE INTERVALS")
    print("="*70)
    print(f"Number of bootstrap samples: {n_bootstrap}")
    
    # Prepare data
    y = excess_returns
    X = factors[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']].copy()
    X['Mom'] = momentum['Mom']
    X = sm.add_constant(X)
    
    # Align data
    data = pd.concat([y, X], axis=1).dropna()
    y_aligned = data.iloc[:, 0].values
    X_aligned = data.iloc[:, 1:].values
    n = len(y_aligned)
    
    # Bootstrap
    bootstrap_params = []
    np.random.seed(42)
    
    for i in range(n_bootstrap):
        # Resample with replacement
        idx = np.random.choice(n, size=n, replace=True)
        y_boot = y_aligned[idx]
        X_boot = X_aligned[idx]
        
        # Fit model
        try:
            model = sm.OLS(y_boot, X_boot).fit()
            bootstrap_params.append(model.params)
        except:
            continue
    
    bootstrap_params = np.array(bootstrap_params)
    
    # Calculate confidence intervals
    ci_95 = np.percentile(bootstrap_params, [2.5, 97.5], axis=0)
    ci_90 = np.percentile(bootstrap_params, [5, 95], axis=0)
    
    factor_names = ['Alpha', 'Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'Mom']
    
    print("\n--- BOOTSTRAP CONFIDENCE INTERVALS ---")
    print(f"{'Factor':<10} {'Mean':>10} {'90% CI':>25} {'95% CI':>25}")
    print("-" * 72)
    
    for i, name in enumerate(factor_names):
        mean = bootstrap_params[:, i].mean()
        ci90 = f"[{ci_90[0, i]:.4f}, {ci_90[1, i]:.4f}]"
        ci95 = f"[{ci_95[0, i]:.4f}, {ci_95[1, i]:.4f}]"
        print(f"{name:<10} {mean:>10.4f} {ci90:>25} {ci95:>25}")
    
    # Check if alpha is significantly different from zero
    alpha_ci = ci_95[:, 0]
    if alpha_ci[0] > 0 or alpha_ci[1] < 0:
        print(f"\n✅ Alpha is significantly different from zero at 95% level")
    else:
        print(f"\n❌ Alpha is NOT significantly different from zero at 95% level")
    
    return {
        'bootstrap_params': bootstrap_params,
        'ci_95': ci_95,
        'ci_90': ci_90,
        'factor_names': factor_names
    }


def run_factor_attribution(ff3_results, ff5_results, ff5_mom_results):
    """
    Analyze factor attribution and model comparison.
    """
    print("\n" + "="*70)
    print("ADVANCED ANALYSIS 4: FACTOR ATTRIBUTION & MODEL COMPARISON")
    print("="*70)
    
    # Create comparison table
    models = [ff3_results, ff5_results, ff5_mom_results]
    model_names = ['FF3', 'FF5', 'FF5+Mom']
    
    print("\n--- MODEL COMPARISON ---")
    print(f"{'Metric':<20} {'FF3':>12} {'FF5':>12} {'FF5+Mom':>12}")
    print("-" * 58)
    
    # R-squared
    r2s = [m['rsquared'] for m in models]
    print(f"{'R²':<20} {r2s[0]:>12.4f} {r2s[1]:>12.4f} {r2s[2]:>12.4f}")
    
    # Adjusted R-squared
    adj_r2s = [m['adj_rsquared'] for m in models]
    print(f"{'Adj R²':<20} {adj_r2s[0]:>12.4f} {adj_r2s[1]:>12.4f} {adj_r2s[2]:>12.4f}")
    
    # AIC
    aics = [m['diagnostics']['aic'] for m in models]
    print(f"{'AIC':<20} {aics[0]:>12.4f} {aics[1]:>12.4f} {aics[2]:>12.4f}")
    
    # BIC
    bics = [m['diagnostics']['bic'] for m in models]
    print(f"{'BIC':<20} {bics[0]:>12.4f} {bics[1]:>12.4f} {bics[2]:>12.4f}")
    
    # Alpha
    alphas = [m['params']['const']*12*100 for m in models]
    print(f"{'Alpha (ann. %)':<20} {alphas[0]:>12.2f} {alphas[1]:>12.2f} {alphas[2]:>12.2f}")
    
    # Number of observations
    nobs = [m['n_obs'] for m in models]
    print(f"{'N Observations':<20} {nobs[0]:>12.0f} {nobs[1]:>12.0f} {nobs[2]:>12.0f}")
    
    print("\n--- MODEL IMPROVEMENT ANALYSIS ---")
    
    # R² improvement from FF3 to FF5
    r2_improvement_ff5 = (r2s[1] - r2s[0]) / (1 - r2s[0]) * 100
    print(f"R² improvement FF3→FF5: {r2_improvement_ff5:.2f}% of unexplained variance")
    
    # R² improvement from FF5 to FF5+Mom
    r2_improvement_mom = (r2s[2] - r2s[1]) / (1 - r2s[1]) * 100
    print(f"R² improvement FF5→FF5+Mom: {r2_improvement_mom:.2f}% of unexplained variance")
    
    # Best model by AIC
    best_aic_idx = np.argmin(aics)
    print(f"\nBest model by AIC: {model_names[best_aic_idx]}")
    
    # Best model by BIC
    best_bic_idx = np.argmin(bics)
    print(f"Best model by BIC: {model_names[best_bic_idx]}")
    
    # Best model by Adjusted R²
    best_adjr2_idx = np.argmax(adj_r2s)
    print(f"Best model by Adj R²: {model_names[best_adjr2_idx]}")
    
    # Factor significance summary
    print("\n--- FACTOR SIGNIFICANCE SUMMARY ---")
    for i, (model, name) in enumerate(zip(models, model_names)):
        print(f"\n{name}:")
        for param, pval in zip(model['params'].index, model['pvalues']):
            sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
            print(f"  {param:<10}: coef={model['params'][param]:>8.4f}, p={pval:.4f} {sig}")
    
    print("\n*** p<0.01, ** p<0.05, * p<0.10")
    
    return {
        'model_names': model_names,
        'r2s': r2s,
        'adj_r2s': adj_r2s,
        'aics': aics,
        'bics': bics
    }


def run_machine_learning_factors(excess_returns, factors, momentum):
    """
    Use Random Forest to identify non-linear factor relationships.
    """
    print("\n" + "="*70)
    print("ADVANCED ANALYSIS 5: MACHINE LEARNING - RANDOM FOREST FACTOR ANALYSIS")
    print("="*70)
    
    # Prepare data
    y = excess_returns
    X = factors[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']].copy()
    X['Mom'] = momentum['Mom']
    
    # Align data
    data = pd.concat([y, X], axis=1).dropna()
    y_aligned = data.iloc[:, 0]
    X_aligned = data.iloc[:, 1:]
    
    # Add non-linear features
    X_enhanced = X_aligned.copy()
    for col in X_aligned.columns:
        X_enhanced[f'{col}_sq'] = X_aligned[col] ** 2
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_enhanced)
    
    # Fit Random Forest
    rf = RandomForestRegressor(n_estimators=500, max_depth=5, 
                               min_samples_leaf=5, random_state=42)
    rf.fit(X_scaled, y_aligned)
    
    # Feature importance (original features only)
    feature_names = list(X_aligned.columns)
    importances = rf.feature_importances_[:len(feature_names)]
    
    print("\n--- RANDOM FOREST FEATURE IMPORTANCE ---")
    print("(Measures non-linear contribution of each factor)")
    print(f"{'Factor':<10} {'Importance':>12} {'Rank':>8}")
    print("-" * 32)
    
    rank_order = np.argsort(importances)[::-1]
    for rank, idx in enumerate(rank_order, 1):
        print(f"{feature_names[idx]:<10} {importances[idx]:>12.4f} {rank:>8}")
    
    # R² from Random Forest
    rf_r2 = rf.score(X_scaled, y_aligned)
    print(f"\nRandom Forest R²: {rf_r2:.4f}")
    
    # Compare with linear R²
    X_linear = sm.add_constant(X_aligned)
    linear_model = sm.OLS(y_aligned, X_linear).fit()
    print(f"Linear Model R²:    {linear_model.rsquared:.4f}")
    print(f"Improvement:        {(rf_r2 - linear_model.rsquared)*100:.2f}%")
    
    if rf_r2 > linear_model.rsquared + 0.05:
        print("\n✅ Significant non-linear relationships detected!")
    else:
        print("\n📊 Linear model captures most of the factor relationships")
    
    return {
        'feature_importance': dict(zip(feature_names, importances)),
        'rf_r2': rf_r2,
        'linear_r2': linear_model.rsquared
    }


# =============================================================================
# SECTION 6: VISUALIZATION FUNCTIONS
# =============================================================================

def create_comprehensive_visualizations(excess_returns, factors, momentum,
                                        ff3_results, ff5_results, ff5_mom_results,
                                        rolling_results, garch_results,
                                        bootstrap_results, attribution_results):
    """
    Create comprehensive visualization of all results.
    """
    fig = plt.figure(figsize=(20, 24))
    
    # 1. Factor Loadings Comparison
    ax1 = fig.add_subplot(4, 3, 1)
    factors_to_plot = ['Mkt-RF', 'SMB', 'HML']
    x = np.arange(len(factors_to_plot))
    width = 0.25
    
    ff3_betas = [ff3_results['params'].get(f, 0) for f in factors_to_plot]
    ff5_betas = [ff5_results['params'].get(f, 0) for f in factors_to_plot]
    
    bars1 = ax1.bar(x - width, ff3_betas, width, label='FF3', alpha=0.8)
    bars2 = ax1.bar(x, ff5_betas, width, label='FF5', alpha=0.8)
    
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax1.set_xlabel('Factor')
    ax1.set_ylabel('Beta Coefficient')
    ax1.set_title('Factor Loadings: FF3 vs FF5', fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(factors_to_plot)
    ax1.legend()
    ax1.bar_label(bars1, fmt='%.2f', fontsize=8)
    ax1.bar_label(bars2, fmt='%.2f', fontsize=8)
    
    # 2. R-squared Comparison
    ax2 = fig.add_subplot(4, 3, 2)
    models = ['FF3', 'FF5', 'FF5+Mom']
    r2s = [ff3_results['rsquared'], ff5_results['rsquared'], ff5_mom_results['rsquared']]
    adj_r2s = [ff3_results['adj_rsquared'], ff5_results['adj_rsquared'], ff5_mom_results['adj_rsquared']]
    
    x = np.arange(len(models))
    bars1 = ax2.bar(x - 0.2, r2s, 0.4, label='R²', color='steelblue')
    bars2 = ax2.bar(x + 0.2, adj_r2s, 0.4, label='Adj R²', color='coral')
    
    ax2.set_ylabel('R-squared')
    ax2.set_title('Model Fit Comparison', fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(models)
    ax2.legend()
    ax2.set_ylim(0, 1)
    for bar in bars1:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=9)
    
    # 3. Alpha Comparison (Annualized)
    ax3 = fig.add_subplot(4, 3, 3)
    alphas = [r['params']['const'] * 12 * 100 for r in [ff3_results, ff5_results, ff5_mom_results]]
    colors = ['green' if a > 0 else 'red' for a in alphas]
    bars = ax3.bar(models, alphas, color=colors, alpha=0.8, edgecolor='black')
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax3.set_ylabel('Annualized Alpha (%)')
    ax3.set_title('Alpha Across Models', fontweight='bold')
    for bar, alpha in zip(bars, alphas):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1 if alpha > 0 
                else bar.get_height() - 0.3, f'{alpha:.2f}%', ha='center', fontsize=10, fontweight='bold')
    
    # 4. Rolling Beta - Market
    ax4 = fig.add_subplot(4, 3, 4)
    if rolling_results is not None:
        rolling_params = rolling_results['rolling_params']
        ax4.plot(rolling_params.index, rolling_params['Mkt-RF'], color='steelblue', linewidth=1.5)
        ax4.fill_between(rolling_params.index, rolling_params['Mkt-RF'], alpha=0.3, color='steelblue')
        ax4.axhline(y=1, color='red', linestyle='--', label='Beta = 1')
        ax4.set_ylabel('Market Beta')
        ax4.set_title(f'Rolling Market Beta ({rolling_results["window"]}M Window)', fontweight='bold')
        ax4.legend()
        ax4.set_ylim(rolling_params['Mkt-RF'].min() - 0.2, rolling_params['Mkt-RF'].max() + 0.2)
    
    # 5. Rolling R-squared
    ax5 = fig.add_subplot(4, 3, 5)
    if rolling_results is not None:
        ax5.plot(rolling_results['rolling_r2'].index, rolling_results['rolling_r2'], 
                color='darkgreen', linewidth=1.5)
        ax5.fill_between(rolling_results['rolling_r2'].index, 
                        rolling_results['rolling_r2'], alpha=0.3, color='darkgreen')
        ax5.set_ylabel('R-squared')
        ax5.set_title(f'Rolling R-squared ({rolling_results["window"]}M Window)', fontweight='bold')
        ax5.set_ylim(0, 1)
    
    # 6. GARCH Conditional Volatility
    ax6 = fig.add_subplot(4, 3, 6)
    if garch_results is not None:
        cond_vol = garch_results['conditional_volatility']
        ax6.plot(cond_vol.index, cond_vol * np.sqrt(12) * 100, color='purple', linewidth=1.5)
        ax6.fill_between(cond_vol.index, cond_vol * np.sqrt(12) * 100, alpha=0.3, color='purple')
        ax6.set_ylabel('Annualized Volatility (%)')
        ax6.set_title('GARCH(1,1) Conditional Volatility', fontweight='bold')
    
    # 7. Bootstrap Coefficient Distribution
    ax7 = fig.add_subplot(4, 3, 7)
    if bootstrap_results is not None:
        boot_params = bootstrap_results['bootstrap_params']
        factor_names = bootstrap_results['factor_names']
        # Plot alpha distribution
        ax7.hist(boot_params[:, 0] * 12 * 100, bins=50, alpha=0.7, color='steelblue', edgecolor='black')
        ax7.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Zero')
        ci = bootstrap_results['ci_95'][:, 0] * 12 * 100
        ax7.axvline(x=ci[0], color='green', linestyle=':', linewidth=2, label=f'95% CI')
        ax7.axvline(x=ci[1], color='green', linestyle=':', linewidth=2)
        ax7.set_xlabel('Annualized Alpha (%)')
        ax7.set_ylabel('Frequency')
        ax7.set_title('Bootstrap Distribution of Alpha', fontweight='bold')
        ax7.legend()
    
    # 8. Residual Diagnostics - QQ Plot
    ax8 = fig.add_subplot(4, 3, 8)
    from scipy import stats
    residuals = ff5_mom_results['model'].resid
    stats.probplot(residuals, dist="norm", plot=ax8)
    ax8.set_title('Q-Q Plot of Residuals (FF5+Mom)', fontweight='bold')
    ax8.get_lines()[0].set_markerfacecolor('steelblue')
    ax8.get_lines()[0].set_markeredgecolor('steelblue')
    
    # 9. Residual Time Series
    ax9 = fig.add_subplot(4, 3, 9)
    ax9.plot(residuals.index, residuals, color='steelblue', linewidth=0.8, alpha=0.8)
    ax9.fill_between(residuals.index, residuals, alpha=0.3, color='steelblue')
    ax9.axhline(y=0, color='red', linestyle='--')
    ax9.axhline(y=2*residuals.std(), color='gray', linestyle=':', alpha=0.7)
    ax9.axhline(y=-2*residuals.std(), color='gray', linestyle=':', alpha=0.7)
    ax9.set_ylabel('Residual')
    ax9.set_title('Residuals Over Time (FF5+Mom)', fontweight='bold')
    
    # 10. Factor Correlation Heatmap
    ax10 = fig.add_subplot(4, 3, 10)
    all_factors = factors[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']].copy()
    all_factors['Mom'] = momentum['Mom']
    corr_matrix = all_factors.corr()
    sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='RdYlBu_r', 
                center=0, ax=ax10, vmin=-1, vmax=1)
    ax10.set_title('Factor Correlation Matrix', fontweight='bold')
    
    # 11. Cumulative Returns vs Fitted
    ax11 = fig.add_subplot(4, 3, 11)
    cum_returns = (1 + excess_returns).cumprod()
    cum_fitted = (1 + ff5_mom_results['model'].fittedvalues).cumprod()
    ax11.plot(cum_returns.index, cum_returns, label='Actual', color='steelblue', linewidth=1.5)
    ax11.plot(cum_fitted.index, cum_fitted, label='Fitted (FF5+Mom)', color='red', 
             linewidth=1.5, linestyle='--')
    ax11.set_ylabel('Cumulative Return')
    ax11.set_title('Actual vs Fitted Cumulative Returns', fontweight='bold')
    ax11.legend()
    ax11.grid(True, alpha=0.3)
    
    # 12. Information Criteria Comparison
    ax12 = fig.add_subplot(4, 3, 12)
    aics = [ff3_results['diagnostics']['aic'], ff5_results['diagnostics']['aic'], 
            ff5_mom_results['diagnostics']['aic']]
    bics = [ff3_results['diagnostics']['bic'], ff5_results['diagnostics']['bic'], 
            ff5_mom_results['diagnostics']['bic']]
    
    x = np.arange(len(models))
    bars1 = ax12.bar(x - 0.2, aics, 0.4, label='AIC', color='steelblue')
    bars2 = ax12.bar(x + 0.2, bics, 0.4, label='BIC', color='coral')
    ax12.set_ylabel('Information Criterion')
    ax12.set_title('Model Selection Criteria', fontweight='bold')
    ax12.set_xticks(x)
    ax12.set_xticklabels(models)
    ax12.legend()
    
    plt.tight_layout()
    plt.savefig('fama_french_analysis.png', dpi=150, bbox_inches='tight')
    print("\n📊 Visualization saved as 'fama_french_analysis.png'")
    plt.show()
    
    return fig


def create_interactive_plot(excess_returns, rolling_results, garch_results):
    """
    Create interactive Plotly visualization.
    """
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=('Cumulative Excess Returns', 
                       'Rolling Market Beta',
                       'GARCH Conditional Volatility'),
        vertical_spacing=0.12
    )
    
    # Cumulative returns
    cum_returns = (1 + excess_returns).cumprod() * 100
    fig.add_trace(
        go.Scatter(x=cum_returns.index, y=cum_returns, 
                   name='Cumulative Return', line=dict(color='steelblue', width=2)),
        row=1, col=1
    )
    
    # Rolling beta
    if rolling_results is not None:
        fig.add_trace(
            go.Scatter(x=rolling_results['rolling_params'].index, 
                      y=rolling_results['rolling_params']['Mkt-RF'],
                      name='Rolling Beta', line=dict(color='darkgreen', width=2)),
            row=2, col=1
        )
        fig.add_hline(y=1, line_dash="dash", line_color="red", row=2, col=1)
    
    # GARCH volatility
    if garch_results is not None:
        cond_vol = garch_results['conditional_volatility'] * np.sqrt(12) * 100
        fig.add_trace(
            go.Scatter(x=cond_vol.index, y=cond_vol,
                      name='Conditional Vol', line=dict(color='purple', width=2),
                      fill='tozeroy', fillcolor='rgba(128, 0, 128, 0.2)'),
            row=3, col=1
        )
    
    fig.update_layout(
        height=900, width=1000,
        title_text="Interactive Fama-French Analysis Dashboard",
        showlegend=True,
        template='plotly_white'
    )
    
    fig.write_html('fama_french_interactive.html')
    print("📊 Interactive visualization saved as 'fama_french_interactive.html'")
    
    return fig


# =============================================================================
# SECTION 7: MAIN EXECUTION
# =============================================================================

def main():
    """
    Main function to run complete Fama-French analysis.
    """
    print("="*70)
    print("   FAMA-FRENCH FACTOR ANALYSIS TOOL")
    print("   FF3 | FF5 | FF5+Momentum | Advanced Analysis")
    print("="*70)
    
    # -------------------------------------------------------------------------
    # CONFIGURATION
    # -------------------------------------------------------------------------
    TICKER = 'AAPL'  # Change this to any stock ticker
    START_DATE = '2015-01-01'
    END_DATE = datetime.now().strftime('%Y-%m-%d')
    ROLLING_WINDOW = 36  # months
    N_BOOTSTRAP = 1000
    
    print(f"\n📋 Configuration:")
    print(f"   Stock: {TICKER}")
    print(f"   Period: {START_DATE} to {END_DATE}")
    print(f"   Rolling Window: {ROLLING_WINDOW} months")
    print(f"   Bootstrap Samples: {N_BOOTSTRAP}")
    
    # -------------------------------------------------------------------------
    # DATA LOADING
    # -------------------------------------------------------------------------
    print("\n📥 Loading data...")
    
    # Get stock data
    stock_returns = get_stock_data(TICKER, START_DATE, END_DATE)
    
    # Get Fama-French factors (includes FF5 factors + RF)
    ff5_factors = get_fama_french_factors(START_DATE, END_DATE, 'F-F_Research_Data_5_Factors_2x3')
    
    # Get momentum factor
    momentum = get_momentum_factor(START_DATE, END_DATE)
    
    # -------------------------------------------------------------------------
    # DATA ALIGNMENT FIX
    # -------------------------------------------------------------------------
    # Yahoo Finance returns DatetimeIndex, Fama-French returns PeriodIndex.
    # We must convert both to the same format to merge them properly.
    
    # -------------------------------------------------------------------------
    # DATA ALIGNMENT FIX
    # -------------------------------------------------------------------------
    # yfinance gives DatetimeIndex -> convert to Period then to Timestamp
    stock_returns.index = stock_returns.index.to_period('M').to_timestamp('M')
    
    # French data gives PeriodIndex -> convert directly to Timestamp
    ff5_factors.index = ff5_factors.index.to_timestamp('M')
    momentum.index = momentum.index.to_timestamp('M')
    
    # FORCE exact column names (strips any hidden spaces from French data)
    stock_returns.columns = ['Return']
    ff5_factors.columns = [c.strip() for c in ff5_factors.columns]
    momentum.columns = ['Mom']
    
    # Merge
    all_data = pd.concat([stock_returns, ff5_factors, momentum], axis=1).dropna()
    
    print(f"\n✅ Aligned data: {len(all_data)} observations")
    print(f"🔍 DEBUG - Columns in all_data: {all_data.columns.tolist()}")  # Debug line
    
    # Calculate excess returns
    excess_returns = all_data['Return'] - all_data['RF']
    factors = all_data[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'RF']]
    momentum_aligned = all_data[['Mom']]
    # Print summary statistics
    print("\n📊 Data Summary Statistics:")
    print(all_data.describe().round(4))
    
    # -------------------------------------------------------------------------
    # STANDARD REGRESSIONS
    # -------------------------------------------------------------------------
    
    # FF3 Regression
    ff3_results = run_ff3_regression(excess_returns, factors)
    
    # FF5 Regression
    ff5_results = run_ff5_regression(excess_returns, factors)
    
    # FF5 + Momentum Regression
    ff5_mom_results = run_ff5_mom_regression(excess_returns, factors, momentum_aligned)
    
    # -------------------------------------------------------------------------
    # ADVANCED ANALYSES
    # -------------------------------------------------------------------------
    
    # 1. Rolling Regression
    rolling_results = run_rolling_regression(excess_returns, factors, momentum_aligned, 
                                            window=ROLLING_WINDOW)
    
    # 2. GARCH Volatility Modeling
    garch_results = run_garch_analysis(excess_returns)
    
    # 3. Bootstrap Confidence Intervals
    bootstrap_results = run_bootstrap_regression(excess_returns, factors, momentum_aligned,
                                                n_bootstrap=N_BOOTSTRAP)
    
    # 4. Factor Attribution & Model Comparison
    attribution_results = run_factor_attribution(ff3_results, ff5_results, ff5_mom_results)
    
    # 5. Machine Learning Factor Analysis
    ml_results = run_machine_learning_factors(excess_returns, factors, momentum_aligned)
    
    # -------------------------------------------------------------------------
    # VISUALIZATIONS
    # -------------------------------------------------------------------------
    print("\n" + "="*70)
    print("GENERATING VISUALIZATIONS")
    print("="*70)
    
    # Static visualizations
    create_comprehensive_visualizations(
        excess_returns, factors, momentum_aligned,
        ff3_results, ff5_results, ff5_mom_results,
        rolling_results, garch_results,
        bootstrap_results, attribution_results
    )
    
    # Interactive visualizations
    create_interactive_plot(excess_returns, rolling_results, garch_results)
    
    # -------------------------------------------------------------------------
    # FINAL SUMMARY
    # -------------------------------------------------------------------------
    print("\n" + "="*70)
    print("EXECUTIVE SUMMARY")
    print("="*70)
    
    print(f"\n📈 Stock Analyzed: {TICKER}")
    print(f"📅 Analysis Period: {START_DATE} to {END_DATE}")
    print(f"📊 Total Observations: {len(all_data)} months")
    
    print(f"\n{'='*50}")
    print("KEY FINDINGS:")
    print(f"{'='*50}")
    
    # Alpha
    print(f"\n1. ALPHA (Risk-Adjusted Return):")
    for name, result in [('FF3', ff3_results), ('FF5', ff5_results), ('FF5+Mom', ff5_mom_results)]:
        alpha_ann = result['params']['const'] * 12 * 100
        t_stat = result['tvalues']['const']
        sig = "✅ Significant" if abs(t_stat) > 2 else "❌ Not Significant"
        print(f"   {name}: {alpha_ann:+.2f}% annualized (t={t_stat:.2f}) - {sig}")
    
    # Factor Exposures
    print(f"\n2. KEY FACTOR EXPOSURES (FF5+Mom):")
    print(f"   Market Beta: {ff5_mom_results['params']['Mkt-RF']:.3f}")
    print(f"   Size (SMB):  {ff5_mom_results['params']['SMB']:+.3f}")
    print(f"   Value (HML): {ff5_mom_results['params']['HML']:+.3f}")
    print(f"   Profitability (RMW): {ff5_mom_results['params']['RMW']:+.3f}")
    print(f"   Investment (CMA): {ff5_mom_results['params']['CMA']:+.3f}")
    print(f"   Momentum (Mom): {ff5_mom_results['params']['Mom']:+.3f}")
    
    # Model Fit
    print(f"\n3. MODEL FIT:")
    print(f"   Best R²: {attribution_results['model_names'][np.argmax(attribution_results['r2s'])]} "
          f"({max(attribution_results['r2s']):.2%})")
    print(f"   Best AIC: {attribution_results['model_names'][np.argmin(attribution_results['aics'])]} "
          f"({min(attribution_results['aics']):.2f})")
    
    # Volatility
    if garch_results:
        print(f"\n4. VOLATILITY DYNAMICS:")
        print(f"   GARCH Persistence: {garch_results['persistence']:.3f}")
        print(f"   → Volatility shocks are {'persistent' if garch_results['persistence'] > 0.9 else 'transient'}")
    
    # Non-linearity
    if ml_results:
        print(f"\n5. NON-LINEARITY:")
        print(f"   RF R²: {ml_results['rf_r2']:.4f} vs Linear R²: {ml_results['linear_r2']:.4f}")
        improvement = (ml_results['rf_r2'] - ml_results['linear_r2']) * 100
        print(f"   → Non-linear improvement: {improvement:.2f}%")
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)
    print("\n📁 Output files:")
    print("   • fama_french_analysis.png - Static visualization")
    print("   • fama_french_interactive.html - Interactive dashboard")
    
    # Return all results for further use
    return {
        'data': all_data,
        'excess_returns': excess_returns,
        'ff3': ff3_results,
        'ff5': ff5_results,
        'ff5_mom': ff5_mom_results,
        'rolling': rolling_results,
        'garch': garch_results,
        'bootstrap': bootstrap_results,
        'attribution': attribution_results,
        'ml': ml_results
    }


if __name__ == "__main__":
    results = main()
