"""
Enhanced Backtesting Module with Advanced Analytics and Risk Management
"""

from typing import Dict, Optional, Tuple, Any, Union
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config.logging_config import logger
import os
import json

class MultiPairBackTester:
    """Enhanced backtester with advanced analytics and risk management"""
    def __init__(
        self,
        strategy: Any,
        prices: pd.DataFrame,
        initial_capital: float = 100000,
        risk_manager: Optional[Any] = None,
        transaction_cost: float = 0.001,
        max_pairs: Optional[int] = None,
        feature_engineer: Optional[Any] = None,
        cointegration_threshold: float = 0.05,
        min_liquidity_threshold: float = 100000
    ):
        self.strategy = strategy
        self.prices = prices.ffill().bfill()
        self.returns = prices.pct_change().ffill().bfill()
        self.initial_capital = initial_capital
        self.risk_manager = risk_manager
        self.transaction_cost = transaction_cost
        self.max_pairs = max_pairs
        self.feature_engineer = feature_engineer
        self.cointegration_threshold = cointegration_threshold
        self.min_liquidity_threshold = min_liquidity_threshold

        self.equity_curve = pd.Series(dtype=float)
        self.current_capital = initial_capital
        self.active_pairs = {}
        self.pair_performance = {}
        self.trade_history = pd.DataFrame()
        self.cointegration_history = {}
        self.feature_history = {}

        self._initialize_components()

    def _initialize_components(self):
        """Initialize strategy components"""
        self.trade_history = pd.DataFrame(
            columns=[
                'Date', 'Pair', 'Action', 'Quantity', 'Price1', 'Price2',
                'Cost', 'Model_Confidence', 'Cointegration_Score',
                'Spread_Zscore', 'Feature_Values'
            ]
        )

        if self.feature_engineer is None:
            from src.data.feature_engineering import FeatureEngineer
            self.feature_engineer = FeatureEngineer()

    def run_backtest(self) -> pd.Series:
        """Execute enhanced backtest with feature engineering and monitoring"""
        logger.info("Starting backtest with enhanced monitoring")
        self.equity_curve = pd.Series(index=self.prices.index, dtype=float)
        portfolio_value = self.initial_capital

        self.equity_curve.iloc[0] = portfolio_value
        features_cache = {}

        for i, current_date in enumerate(self.prices.index[1:], 1):
            try:
                historical_prices = self.prices.iloc[:i + 1]
                if i % 20 == 0:
                    features = self._prepare_features(historical_prices)
                    features_cache = features
                else:
                    features = features_cache

                signals = (
                    self.strategy.predict_signals(features)
                    if hasattr(self.strategy, 'predict_signals')
                    else self.strategy.generate_signals(historical_prices)
                )

                portfolio_value = self._process_signals_and_update(
                    signals,
                    portfolio_value,
                    current_date,
                    features
                )

                self.equity_curve.loc[current_date] = portfolio_value

                if self.risk_manager and self.risk_manager.check_risk_limits(
                    self.equity_curve,
                    self.active_pairs,
                    self.prices.loc[current_date].to_dict()
                )[0]:
                    logger.warning(f"Risk limits exceeded at {current_date}")
                    break

            except Exception as e:
                logger.error(f"Error in backtest at {current_date}: {str(e)}")
                continue

        logger.info("Backtest completed")
        return self.equity_curve


    def _prepare_features(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Prepare features using feature engineering"""
        try:
            features = self.feature_engineer.generate_features(prices)
            return features
        except Exception as e:
            logger.error(f"Feature engineering failed: {str(e)}")
            return prices

    def _process_signals_and_update(
            self,
            signals: Union[pd.DataFrame, Dict[Tuple[str, str], pd.Series]],
            portfolio_value: float,
            current_date: pd.Timestamp,
            features: pd.DataFrame
    ) -> float:
        """
        Process signals with enhanced monitoring and updates.

        Args:
            signals: Either DataFrame with pair columns or Dict mapping pairs to signal Series
            portfolio_value: Current portfolio value
            current_date: Current timestamp
            features: Feature DataFrame

        Returns:
            float: Updated portfolio value
        """
        current_prices = self.prices.loc[current_date]

        if isinstance(signals, pd.DataFrame) and not 'predicted_signal' in signals.columns:
            for pair in signals.columns:
                if isinstance(pair, tuple) and len(pair) == 2:
                    asset1, asset2 = pair
                    if asset1 not in current_prices or asset2 not in current_prices:
                        continue

                    signal_value = float(signals[pair].loc[current_date])

                    confidence = 1.0
                    if isinstance(features, pd.DataFrame) and 'confidence' in features.columns:
                        confidence = float(features['confidence'].iloc[-1])

                    if self.risk_manager:
                        self.risk_manager.update_risk_metrics(
                            pair,
                            self.prices,
                            self.active_pairs,
                            confidence
                        )

                    portfolio_value = self._process_pair_signal(
                        pair,
                        signal_value,
                        portfolio_value,
                        current_date,
                        confidence,
                        features
                    )

        elif isinstance(signals, pd.DataFrame) and 'predicted_signal' in signals.columns:
            for pair in self.strategy.pairs:
                if isinstance(pair, tuple) and len(pair) == 2:
                    asset1, asset2 = pair
                    if asset1 not in current_prices or asset2 not in current_prices:
                        continue

                    pair_signals = signals[signals['Pair'] == f"{asset1}/{asset2}"]
                    if not pair_signals.empty:
                        signal_value = float(pair_signals.iloc[-1]['predicted_signal'])
                        confidence = float(pair_signals.iloc[-1].get('confidence', 1.0))

                        if self.risk_manager:
                            self.risk_manager.update_risk_metrics(
                                pair,
                                self.returns,
                                self.active_pairs,
                                confidence
                            )

                        portfolio_value = self._process_pair_signal(
                            pair,
                            signal_value,
                            portfolio_value,
                            current_date,
                            confidence,
                            features
                        )

        else:
            for pair, signal_row in signals.items():
                if isinstance(pair, tuple) and len(pair) == 2:
                    asset1, asset2 = pair
                    if asset1 not in current_prices or asset2 not in current_prices:
                        continue

                    signal_value = float(signal_row.loc[current_date])
                    confidence = 1.0

                    if self.risk_manager:
                        self.risk_manager.update_risk_metrics(
                            pair,
                            self.returns,
                            self.active_pairs,
                            confidence
                        )

                    portfolio_value = self._process_pair_signal(
                        pair,
                        signal_value,
                        portfolio_value,
                        current_date,
                        confidence,
                        features
                    )

        return portfolio_value

    def _process_pair_signal(
        self,
        pair: Tuple[str, str],
        signal: float,
        portfolio_value: float,
        current_date: pd.Timestamp,
        confidence: float,
        features: pd.DataFrame
    ) -> float:
        """Process signal for a single pair"""
        if pair in self.active_pairs:
            existing_signal = self.active_pairs[pair]['signal']
            if signal == 0 or (signal * existing_signal < 0):
                portfolio_value = self._close_position(
                    pair,
                    portfolio_value,
                    current_date,
                    "Signal change"
                )

        if signal != 0 and pair not in self.active_pairs:
            if self.risk_manager and confidence < self.risk_manager.min_model_confidence:
                return portfolio_value

            quantity = (
                self.risk_manager.calculate_position_size(
                    portfolio_value,
                    pair,
                    self.returns,
                    confidence,
                    self.returns.corr()
                )
                if self.risk_manager
                else portfolio_value * self.strategy.max_position_size
            )

            if self._validate_pair_trade(pair, quantity, current_date):
                portfolio_value = self._open_position(
                    pair,
                    signal,
                    quantity,
                    portfolio_value,
                    current_date,
                    confidence,
                    features
                )

        return portfolio_value

    def _validate_pair_trade(
        self,
        pair: Tuple[str, str],
        quantity: float,
        current_date: pd.Timestamp
    ) -> bool:
        """Validate if a pair trade meets all requirements"""
        if not quantity > 0:
            return False

        if self.max_pairs and len(self.active_pairs) >= self.max_pairs:
            return False

        asset1, asset2 = pair
        return asset1 in self.returns.columns and asset2 in self.returns.columns

    def _open_position(
        self,
        pair: Tuple[str, str],
        signal: float,
        quantity: float,
        portfolio_value: float,
        current_date: pd.Timestamp,
        confidence: float,
        features: pd.DataFrame
    ) -> float:
        """Open new position with proper price-based calculations."""
        asset1, asset2 = pair
        price1 = self.prices[asset1].loc[current_date]
        price2 = self.prices[asset2].loc[current_date]

        position_value = abs(quantity) * (price1 + price2)
        total_cost = position_value * self.transaction_cost

        if position_value + total_cost > portfolio_value:
            logger.warning(f"Insufficient capital for position in {pair}")
            return portfolio_value

        self.active_pairs[pair] = {
            'signal': signal,
            'quantity': quantity,
            'entry_date': current_date,
            'entry_prices': (price1, price2),
            'confidence': confidence,
            'features': features.iloc[-1].to_dict() if not features.empty else {},
            'transaction_costs': total_cost
        }

        self.trade_history = pd.concat([
            self.trade_history,
            pd.DataFrame([{
                'Date': current_date,
                'Pair': f"{asset1}/{asset2}",
                'Action': 'ENTRY',
                'Quantity': quantity * signal,
                'Price1': price1,
                'Price2': price2,
                'Cost': total_cost,
                'Model_Confidence': confidence,
                'Feature_Values': str(features.iloc[-1].to_dict() if not features.empty else {})
            }])
        ], ignore_index=True)

        return portfolio_value - total_cost - position_value

    def _close_position(
        self,
        pair: Tuple[str, str],
        portfolio_value: float,
        current_date: pd.Timestamp,
        reason: str = None
    ) -> float:
        """Close position"""
        if pair not in self.active_pairs:
            return portfolio_value

        position = self.active_pairs[pair]
        asset1, asset2 = pair

        entry_price1, entry_price2 = position['entry_prices']
        current_price1 = self.returns[asset1].loc[current_date]
        current_price2 = self.returns[asset2].loc[current_date]

        entry_spread = entry_price1 - entry_price2
        exit_spread = current_price1 - current_price2
        spread_pnl = position['quantity'] * position['signal'] * (
            exit_spread - entry_spread
        )

        exit_value = position['quantity'] * (current_price1 + current_price2)
        exit_cost = exit_value * self.transaction_cost
        total_pnl = spread_pnl - position['transaction_costs'] - exit_cost

        self.trade_history = pd.concat([
            self.trade_history,
            pd.DataFrame([{
                'Date': current_date,
                'Pair': f"{asset1}/{asset2}",
                'Action': 'EXIT',
                'Reason': reason,
                'Quantity': -position['quantity'] * position['signal'],
                'Price1': current_price1,
                'Price2': current_price2,
                'Cost': exit_cost,
                'PnL': total_pnl,
                'Model_Confidence': position['confidence']
            }])
        ], ignore_index=True)

        if pair not in self.pair_performance:
            self.pair_performance[pair] = []

        self.pair_performance[pair].append({
            'Entry_Date': position['entry_date'],
            'Exit_Date': current_date,
            'Holding_Period': (current_date - position['entry_date']).days,
            'PnL': total_pnl,
            'Return': total_pnl / exit_value,
            'Model_Confidence': position['confidence'],
            'Exit_Reason': reason
        })

        del self.active_pairs[pair]
        return portfolio_value + total_pnl

    def generate_report(self, output_file: Optional[str] = None) -> Dict:
        """Generate comprehensive backtest report"""
        metrics = self._calculate_performance_metrics()

        report = {
            'Overall_Metrics': metrics,
            'Pair_Performance': self._analyze_pair_performance(),
            'Risk_Analysis': self._analyze_risk_metrics()
        }

        if output_file:
            self._save_report(report, output_file)

        return report

    def _calculate_performance_metrics(self) -> Dict:
        """Calculate key performance metrics"""
        if len(self.equity_curve) < 2:
            return {
                'Total Return': 0.0,
                'Annual Return': 0.0,
                'Annual Volatility': 0.0,
                'Sharpe Ratio': 0.0,
                'Max Drawdown': 0.0,
                'Win Rate': 0.0
            }

        returns = self.equity_curve.pct_change().dropna()

        return {
            'Total_Return': (self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1),
            'Annual_Return': returns.mean() * 252,
            'Annual_Volatility': returns.std() * np.sqrt(252),
            'Sharpe_Ratio': (returns.mean() / returns.std()) * np.sqrt(252),
            'Max_Drawdown': self.risk_manager.calculate_drawdown(self.equity_curve) if self.risk_manager else None,
            'Win_Rate': len([t for t in self.trade_history['PnL'] if t > 0]) / len(self.trade_history) if len(self.trade_history) > 0 else 0
        }

    def _analyze_pair_performance(self) -> Dict[str, Dict[str, float]]:
        """Analyze performance metrics for each pair"""
        pair_analysis = {}

        for pair, trades in self.pair_performance.items():
            if not trades:
                continue

            trades_df = pd.DataFrame(trades)
            pair_analysis[f"{pair[0]}/{pair[1]}"] = {
                'Total_PnL': trades_df['PnL'].sum(),
                'Number_of_Trades': len(trades),
                'Win_Rate': (trades_df['PnL'] > 0).mean(),
                'Average_Return': trades_df['Return'].mean(),
                'Average_Holding_Period': trades_df['Holding_Period'].mean(),
                'Average_Confidence': trades_df['Model_Confidence'].mean()
            }

        return pair_analysis

    def _analyze_risk_metrics(self) -> Dict:
        """Get risk metrics from risk manager"""
        if not self.risk_manager:
            return {}

        return {
            pair: metrics.__dict__
            for pair, metrics in self.risk_manager.risk_metrics.items()
        }

    def _save_report(self, report: Dict, output_file: str) -> None:
        """Save backtest report to file"""
        try:
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            with open(output_file, 'w') as f:
                json.dump(report, f, indent=4, default=str)

            logger.info(f"Report saved successfully to {output_file}")

        except Exception as e:
            logger.error(f"Error saving report: {str(e)}")
            raise


class BacktestVisualizer:
    """Component for generating interactive backtest visualizations"""

    def plot_all_analysis(self, backtest) -> None:
        """Generate all analysis plots"""
        logger.info("Generating comprehensive analysis plots")

        self.plot_performance(backtest)
        for pair in backtest.pair_performance:
            self.plot_pair_analysis(backtest, pair)
        if backtest.risk_manager:
            backtest.risk_manager.plot_risk_metrics()
        self.plot_trading_metrics(backtest)

    def plot_performance(self, backtest, show_trades: bool = True) -> None:
        """Plot trading performance metrics"""
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=(
                'Equity Curve with Trade Points',
                'Rolling Returns & Volatility',
                'Trade Analysis'
            ),
            row_heights=[0.5, 0.25, 0.25]
        )

        fig.add_trace(
            go.Scatter(
                x=backtest.equity_curve.index,
                y=backtest.equity_curve.values,
                name='Portfolio Value',
                line=dict(color='blue')
            ),
            row=1, col=1
        )

        if show_trades and not backtest.trade_history.empty:
            entries = backtest.trade_history[backtest.trade_history['Action'] == 'ENTRY']
            fig.add_trace(
                go.Scatter(
                    x=entries['Date'],
                    y=[backtest.equity_curve[date] for date in entries['Date']],
                    mode='markers',
                    name='Trade Entry',
                    marker=dict(color='green', symbol='triangle-up', size=10),
                    text=[f"Pair: {p}<br>Size: {q}<br>Conf: {c}"
                          for p, q, c in zip(entries['Pair'], entries['Quantity'],
                                             entries['Model_Confidence'])],
                    hoverinfo='text'
                ),
                row=1, col=1
            )

            exits = backtest.trade_history[backtest.trade_history['Action'] == 'EXIT']
            fig.add_trace(
                go.Scatter(
                    x=exits['Date'],
                    y=[backtest.equity_curve[date] for date in exits['Date']],
                    mode='markers',
                    name='Trade Exit',
                    marker=dict(color='red', symbol='triangle-down', size=10),
                    text=[f"Pair: {p}<br>PnL: {pnl:.2f}<br>Reason: {r}"
                          for p, pnl, r in zip(exits['Pair'], exits['PnL'], exits['Reason'])],
                    hoverinfo='text'
                ),
                row=1, col=1
            )

            if backtest.risk_manager:
                drawdown = pd.Series(index=backtest.equity_curve.index)
                for date in backtest.equity_curve.index:
                    drawdown[date] = backtest.risk_manager.calculate_drawdown(
                        backtest.equity_curve[:date])

                fig.add_trace(
                    go.Scatter(
                        x=drawdown.index,
                        y=drawdown.values * 100,
                        name='Drawdown %',
                        fill='tozeroy',
                        line=dict(color='red')
                    ),
                    row=1, col=1
                )

        returns = backtest.equity_curve.pct_change()
        rolling_returns = returns.rolling(window=20).mean() * 252 * 100
        rolling_vol = returns.rolling(window=20).std() * np.sqrt(252) * 100

        fig.add_trace(
            go.Scatter(
                x=rolling_returns.index,
                y=rolling_returns.values,
                name='Rolling Returns (Ann.)',
                line=dict(color='green')
            ),
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=rolling_vol.index,
                y=rolling_vol.values,
                name='Rolling Vol (Ann.)',
                line=dict(color='orange')
            ),
            row=2, col=1
        )

        if not backtest.trade_history.empty:
            trade_pnls = backtest.trade_history[
                backtest.trade_history['Action'] == 'EXIT']['PnL']
            fig.add_trace(
                go.Bar(
                    x=trade_pnls.index,
                    y=trade_pnls.values,
                    name='Trade PnL',
                    marker=dict(
                        color=['green' if x > 0 else 'red' for x in trade_pnls]
                    )
                ),
                row=3, col=1
            )

        fig.update_layout(
            height=900,
            title_text='Trading Performance Analysis',
            showlegend=True
        )

        fig.update_yaxes(title_text="Portfolio Value", row=1, col=1)
        fig.update_yaxes(title_text="Percentage", row=2, col=1)
        fig.update_yaxes(title_text="PnL", row=3, col=1)
        fig.update_xaxes(title_text="Date", row=3, col=1)

        fig.show()

    def plot_pair_analysis(self, backtest, pair: Optional[Tuple[str, str]] = None) -> None:
        """Plot pair-specific trading analysis"""
        if pair and pair not in backtest.pair_performance:
            logger.warning(f"No data available for pair {pair}")
            return

        pairs_to_analyze = [pair] if pair else list(backtest.pair_performance.keys())

        for current_pair in pairs_to_analyze:
            trades = pd.DataFrame(backtest.pair_performance[current_pair])
            if trades.empty:
                continue

            fig = make_subplots(
                rows=2,
                cols=2,
                subplot_titles=(
                    'Cumulative PnL',
                    'Trade Size vs Returns',
                    'Trade Duration Analysis',
                    'Monthly Performance'
                )
            )

            cumulative_pnl = trades['PnL'].cumsum()
            peak = cumulative_pnl.expanding().max()
            drawdown = (cumulative_pnl - peak) / peak * 100

            fig.add_trace(
                go.Scatter(
                    x=trades['Exit_Date'],
                    y=cumulative_pnl,
                    name='Cumulative PnL'
                ),
                row=1, col=1
            )

            fig.add_trace(
                go.Scatter(
                    x=trades['Exit_Date'],
                    y=drawdown,
                    name='Drawdown',
                    fill='tozeroy',
                    line=dict(color='red')
                ),
                row=1, col=1
            )

            fig.add_trace(
                go.Scatter(
                    x=trades['Quantity'].abs(),
                    y=trades['Return'],
                    mode='markers',
                    name='Size vs Returns',
                    marker=dict(
                        color=trades['PnL'],
                        colorscale='RdYlGn',
                        showscale=True
                    )
                ),
                row=1, col=2
            )

            fig.add_trace(
                go.Box(
                    y=trades['Holding_Period'],
                    name='Holding Period',
                    boxpoints='all',
                    jitter=0.3,
                    pointpos=-1.8
                ),
                row=2, col=1
            )

            monthly_stats = trades.set_index('Exit_Date').resample('M').agg({
                'PnL': ['sum', 'count', lambda x: (x > 0).mean() * 100]
            })

            fig.add_trace(
                go.Bar(
                    x=monthly_stats.index,
                    y=monthly_stats['PnL']['sum'],
                    name='Monthly PnL'
                ),
                row=2, col=2
            )

            fig.add_trace(
                go.Scatter(
                    x=monthly_stats.index,
                    y=monthly_stats['PnL']['<lambda_0>'],
                    name='Win Rate %',
                    yaxis='y2',
                    line=dict(color='green')
                ),
                row=2, col=2
            )

            fig.update_layout(
                height=800,
                title_text=f'Trading Analysis: {current_pair[0]}/{current_pair[1]}',
                showlegend=True,
            )

            fig.update_layout(
                yaxis4=dict(
                    title='Win Rate %',
                    overlaying='y3',
                    side='right',
                    range=[0, 100]
                )
            )

            fig.show()

    def plot_trading_metrics(self, backtest) -> None:
        """Plot trading-specific metrics analysis"""
        if backtest.trade_history.empty:
            logger.warning("No trade history available for analysis")
            return

        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                'Trade Size Distribution',
                'Duration vs PnL',
                'Win Rate by Month',
                'Trading Activity'
            )
        )

        trade_sizes = backtest.trade_history[
            backtest.trade_history['Action'] == 'ENTRY']['Quantity'].abs()
        fig.add_trace(
            go.Histogram(
                x=trade_sizes,
                name='Trade Sizes',
                nbinsx=30
            ),
            row=1, col=1
        )

        exits = backtest.trade_history[backtest.trade_history['Action'] == 'EXIT']
        fig.add_trace(
            go.Scatter(
                x=exits['Holding_Period'],
                y=exits['PnL'],
                mode='markers',
                name='Duration vs PnL',
                marker=dict(
                    color=exits['Model_Confidence'],
                    colorscale='Viridis',
                    showscale=True
                )
            ),
            row=1, col=2
        )

        monthly_trades = exits.set_index('Date').resample('M').agg({
            'PnL': lambda x: (x > 0).mean() * 100
        })

        fig.add_trace(
            go.Scatter(
                x=monthly_trades.index,
                y=monthly_trades['PnL'],
                name='Monthly Win Rate %'
            ),
            row=2, col=1
        )

        trade_counts = exits.set_index('Date').resample('M').size()
        fig.add_trace(
            go.Bar(
                x=trade_counts.index,
                y=trade_counts.values,
                name='Monthly Trades'
            ),
            row=2, col=2
        )

        fig.update_layout(
            height=800,
            title_text='Trading Metrics Analysis',
            showlegend=True
        )

        fig.show()