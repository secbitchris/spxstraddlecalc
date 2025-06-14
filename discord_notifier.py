import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
import aiohttp
import pytz
from dotenv import load_dotenv
from gist_publisher import GistPublisher

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class DiscordNotifier:
    """
    Discord webhook notification service for SPX straddle calculations
    
    Sends formatted messages to Discord channels using webhooks.
    Much simpler than bot tokens - just needs a webhook URL.
    """
    
    def __init__(self, webhook_url: str = None):
        """
        Initialize Discord notifier
        
        Args:
            webhook_url: Discord webhook URL
        """
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.enabled = bool(self.webhook_url)
        self.session = None
        self.gist_publisher = GistPublisher()
        
        if not self.enabled:
            logger.warning("Discord webhook URL not provided - notifications disabled")
        else:
            logger.info("Discord webhook notifications enabled")
    
    async def initialize(self):
        """Initialize webhook (no setup needed for webhooks)"""
        if self.enabled:
            logger.info("Discord webhook notifier initialized")
        else:
            logger.info("Discord notifications disabled")
    
    async def close(self):
        """Close webhook (no cleanup needed for webhooks)"""
        pass
    
    def format_straddle_message(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format straddle calculation result into Discord webhook payload
        
        Args:
            result: Straddle calculation result
            
        Returns:
            Discord webhook payload dict
        """
        try:
            et_tz = pytz.timezone('US/Eastern')
            timestamp = datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S ET')
            
            if 'error' in result:
                return {
                    "content": f"🚨 **SPX Straddle Calculation Error**\n```\nError: {result['error']}\nTime: {timestamp}\n```"
                }
            
            # Success message
            straddle_cost = result.get('straddle_cost', 0)
            spx_price = result.get('spx_price_930am', 0)
            atm_strike = result.get('atm_strike', 0)
            call_price = result.get('call_price_931am', 0)
            put_price = result.get('put_price_931am', 0)
            calc_date = result.get('calculation_date', 'Unknown')
            
            # Create formatted message with emojis and styling
            content = f"""📊 **SPX 0DTE Straddle Cost - {calc_date}**

💰 **Total Straddle Cost: ${straddle_cost:.2f}**

📈 **Market Data:**
• SPX @ 9:30 AM: ${spx_price:.2f}
• ATM Strike: {atm_strike}

🎯 **Option Prices @ 9:31 AM:**
• Call: ${call_price:.2f}
• Put: ${put_price:.2f}

⏰ **Calculated:** {timestamp}
"""
            
            # Add cost analysis
            if straddle_cost > 0:
                if straddle_cost < 30:
                    content += "\n💡 **Analysis:** Low cost straddle - potential opportunity"
                elif straddle_cost > 60:
                    content += "\n⚠️ **Analysis:** High cost straddle - elevated volatility expected"
                else:
                    content += "\n📊 **Analysis:** Moderate cost straddle"
            
            return {"content": content}
            
        except Exception as e:
            logger.error(f"Error formatting straddle message: {e}")
            return {"content": f"❌ Error formatting straddle data: {str(e)}"}
    
    def format_statistics_message(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format statistics into Discord webhook payload
        
        Args:
            stats: Statistics calculation result
            
        Returns:
            Discord webhook payload dict
        """
        try:
            if stats.get('status') != 'success':
                return {"content": f"❌ **Statistics Error:** {stats.get('error_message', 'Unknown error')}"}
            
            desc_stats = stats.get('descriptive_stats', {})
            trend = stats.get('trend_analysis', {})
            volatility = stats.get('volatility_analysis', {})
            recent = stats.get('recent_comparison', {})
            period = stats.get('period_days', 30)
            
            content = f"""📈 **SPX Straddle Statistics ({period} days)**

📊 **Descriptive Stats:**
• Average: ${desc_stats.get('mean', 0):.2f}
• Median: ${desc_stats.get('median', 0):.2f}
• Range: ${desc_stats.get('min', 0):.2f} - ${desc_stats.get('max', 0):.2f}
• Std Dev: ${desc_stats.get('std_dev', 0):.2f}

📉 **Trend Analysis:**
• Direction: {trend.get('direction', 'Unknown').title()}
• {trend.get('interpretation', '')}

🎢 **Volatility:**
• Category: {volatility.get('category', 'Unknown').title()}
• {volatility.get('interpretation', '')}

🔄 **Recent vs Historical:**
• 7-day avg: ${recent.get('recent_7day_avg', 0):.2f}
• Change: {recent.get('percentage_change', 0):+.1f}%
"""
            
            return {"content": content}
            
        except Exception as e:
            logger.error(f"Error formatting statistics message: {e}")
            return {"content": f"❌ Error formatting statistics: {str(e)}"}
    
    def format_multi_timeframe_message(self, multi_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format multi-timeframe statistics into Discord webhook payload with Gist link
        
        Args:
            multi_stats: Multi-timeframe statistics result
            
        Returns:
            Discord webhook payload dict
        """
        try:
            if multi_stats.get('status') != 'success':
                return {"content": f"❌ **Multi-Timeframe Statistics Error:** {multi_stats.get('error', 'Unknown error')}"}
            
            timeframes = multi_stats.get('timeframes', {})
            summary = multi_stats.get('summary', {})
            
            # Get key timeframes for Discord (focused on most important: 1D, 3D, 7D, 30D, YTD)
            key_periods = ['1d', '3d', '7d', '30d', 'ytd']
            available_periods = [p for p in key_periods if p in timeframes]
            
            if not available_periods:
                return {"content": "❌ **No multi-timeframe data available**"}
            
            # Create focused analysis content
            content = f"""📊 **SPX 0DTE Straddle Multi-Timeframe Volatility Analysis**

🔍 **Key Timeframes - Daily to YTD Progression:**
"""
            
            # Add key timeframe analysis
            for period in available_periods:
                tf_data = timeframes[period]
                data_points = tf_data.get('data_points', 0)
                avg_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
                trend = tf_data.get('trend_analysis', {}).get('direction', 'unknown')
                
                # Skip if insufficient data
                if data_points < 5:
                    continue
                
                # Trend emoji
                trend_emoji = {
                    'increasing': '📈',
                    'decreasing': '📉', 
                    'stable': '➡️'
                }.get(trend, '❓')
                
                # Period-specific insights for focused timeframes
                if period == 'ytd':
                    period_label = tf_data.get('period_label', 'YTD')
                    insight = "Current year performance"
                elif period == '1d':
                    insight = "Today's momentum"
                elif period == '3d':
                    insight = "Very short-term"
                elif period == '7d':
                    insight = "Weekly momentum"
                elif period == '30d':
                    insight = "Monthly trend"
                else:
                    insight = "Historical perspective"
                
                content += f"**{period_label if period == 'ytd' else period.upper()}**: ${avg_cost:.2f} avg {trend_emoji} ({insight})\n"
            
            # Add market insights
            content += "\n💡 **Key Market Insights:**\n"
            
            # YTD vs long-term comparison
            if 'ytd' in timeframes and '720d' in timeframes:
                ytd_avg = timeframes['ytd'].get('descriptive_stats', {}).get('mean', 0)
                longterm_avg = timeframes['720d'].get('descriptive_stats', {}).get('mean', 0)
                
                if ytd_avg > 0 and longterm_avg > 0:
                    pct_diff = ((ytd_avg - longterm_avg) / longterm_avg) * 100
                    if abs(pct_diff) > 10:
                        comparison = "significantly elevated" if pct_diff > 0 else "significantly below"
                        ytd_label = timeframes['ytd'].get('period_label', 'YTD')
                        content += f"• **{ytd_label} is {pct_diff:+.1f}% vs long-term** ({comparison})\n"
            
            # Trend analysis
            if '30d' in timeframes and '7d' in timeframes:
                short_trend = timeframes['7d'].get('trend_analysis', {}).get('direction', 'unknown')
                medium_trend = timeframes['30d'].get('trend_analysis', {}).get('direction', 'unknown')
                
                if short_trend == 'decreasing' and medium_trend == 'decreasing':
                    content += "• **Consistent cooling** across timeframes\n"
                elif short_trend == 'increasing' and medium_trend == 'increasing':
                    content += "• **Building momentum** across timeframes\n"
                elif short_trend != medium_trend:
                    content += "• **Mixed trends** - complex volatility environment\n"
                else:
                    content += "• **Short-term cooling** from recent highs\n"
            
            # Data coverage
            total_data_points = summary.get('total_data_points', 0)
            if total_data_points > 0:
                content += f"• **Total historical data:** {total_data_points} trading days analyzed\n"
            
            # Volatility environment (use YTD if available, otherwise 30D)
            vol_period = 'ytd' if 'ytd' in timeframes else '30d' if '30d' in timeframes else None
            if vol_period and vol_period in timeframes:
                vol_analysis = timeframes[vol_period].get('volatility_analysis', {})
                ytd_vol = vol_analysis.get('category', 'unknown')
                ytd_cv = vol_analysis.get('coefficient_of_variation', 0)
                
                vol_emoji = {
                    'low': '🟢',
                    'medium': '🟡', 
                    'high': '🔴'
                }.get(ytd_vol, '⚪')
                
                if ytd_vol == 'high':
                    vol_insight = "elevated volatility regime"
                elif ytd_vol == 'medium':
                    vol_insight = "moderate volatility environment"
                else:
                    vol_insight = "low volatility regime"
                
                content += f"\n🎢 **Volatility Environment:**"
                content += f" {vol_emoji} **{ytd_vol.title()}** ({ytd_cv:.1f}% CV) - {vol_insight}"
            
            # Add placeholder for Gist link (will be updated after Gist creation)
            content += f"""

📋 **Full Analysis:** Creating detailed report...
🔗 Link will be updated shortly"""
            
            return {"content": content, "needs_gist": True, "multi_stats": multi_stats}
            
        except Exception as e:
            logger.error(f"Error formatting multi-timeframe message: {e}")
            return {"content": f"❌ Error formatting multi-timeframe statistics: {str(e)}"}
    
    def format_daily_timeframe_message(self, multi_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format daily timeframe statistics (1D-14D) into Discord webhook payload
        
        Args:
            multi_stats: Multi-timeframe statistics result
            
        Returns:
            Discord webhook payload dict
        """
        try:
            if multi_stats.get('status') != 'success':
                return {"content": f"❌ **Daily Timeframe Statistics Error:** {multi_stats.get('error', 'Unknown error')}"}
            
            timeframes = multi_stats.get('timeframes', {})
            summary = multi_stats.get('summary', {})
            
            # Get daily timeframes (1D-14D)
            daily_periods = [f'{i}d' for i in range(1, 15)]
            available_daily = [p for p in daily_periods if p in timeframes]
            
            if not available_daily:
                return {"content": "❌ **No daily timeframe data available**"}
            
            content = f"""📊 **SPX 0DTE Straddle Daily Momentum Analysis**

🔍 **Short-term Volatility Tracking (1D-14D):**
"""
            
            # Add daily timeframe analysis
            for period in available_daily:
                tf_data = timeframes[period]
                data_points = tf_data.get('data_points', 0)
                avg_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
                trend = tf_data.get('trend_analysis', {}).get('direction', 'unknown')
                
                # Skip if insufficient data
                if data_points < 1:
                    continue
                
                # Trend emoji
                trend_emoji = {
                    'increasing': '📈',
                    'decreasing': '📉', 
                    'stable': '➡️'
                }.get(trend, '❓')
                
                # Daily-specific insights
                period_num = int(period.replace('d', ''))
                if period_num == 1:
                    insight = "Today vs yesterday"
                elif period_num <= 3:
                    insight = "Very short-term"
                elif period_num <= 7:
                    insight = "Weekly momentum"
                else:
                    insight = "Two-week trend"
                
                content += f"**{period.upper()}**: ${avg_cost:.2f} avg {trend_emoji} ({insight})\n"
            
            # Add momentum analysis
            momentum_analysis = ""
            if '1d' in timeframes and '7d' in timeframes and '14d' in timeframes:
                today_avg = timeframes['1d'].get('descriptive_stats', {}).get('mean', 0)
                week_avg = timeframes['7d'].get('descriptive_stats', {}).get('mean', 0)
                twoweek_avg = timeframes['14d'].get('descriptive_stats', {}).get('mean', 0)
                
                if today_avg > week_avg > twoweek_avg:
                    momentum_analysis = "• **Accelerating upward** momentum"
                elif today_avg < week_avg < twoweek_avg:
                    momentum_analysis = "• **Accelerating downward** momentum"
                elif today_avg > week_avg and week_avg < twoweek_avg:
                    momentum_analysis = "• **Recent reversal** to upside"
                elif today_avg < week_avg and week_avg > twoweek_avg:
                    momentum_analysis = "• **Recent reversal** to downside"
                else:
                    momentum_analysis = f"• **Mixed signals** - today ${today_avg:.2f} vs week ${week_avg:.2f}"
            
            # Volatility regime analysis
            vol_analysis = ""
            if '7d' in timeframes:
                week_vol = timeframes['7d'].get('volatility_analysis', {}).get('category', 'unknown')
                week_cv = timeframes['7d'].get('volatility_analysis', {}).get('coefficient_of_variation', 0)
                vol_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(week_vol, '⚪')
                
                if week_vol == 'high':
                    vol_insight = "elevated short-term volatility"
                elif week_vol == 'medium':
                    vol_insight = "moderate short-term volatility"
                else:
                    vol_insight = "low short-term volatility"
                
                vol_analysis = f"• **7D volatility:** {vol_emoji} {week_vol.title()} ({week_cv:.1f}% CV)"
            
            content += f"""
💡 **Daily Momentum Insights:**
{momentum_analysis}
{vol_analysis}
• **Data points analyzed:** {len(available_daily)} daily timeframes

⚡ **Trading Implications:** Short-term momentum {'building' if 'upward' in momentum_analysis else 'cooling' if 'downward' in momentum_analysis else 'mixed'}"""
            
            return {"content": content}
            
        except Exception as e:
            logger.error(f"Error formatting daily timeframe message: {e}")
            return {"content": f"❌ Error formatting daily timeframe statistics: {str(e)}"}
    
    def format_error_message(self, error: str, context: str = "SPX Straddle") -> Dict[str, Any]:
        """
        Format error message for Discord webhook
        
        Args:
            error: Error message
            context: Context of the error
            
        Returns:
            Discord webhook payload dict
        """
        et_tz = pytz.timezone('US/Eastern')
        timestamp = datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S ET')
        
        return {
            "content": f"""🚨 **{context} Error**
```
{error}
```
⏰ **Time:** {timestamp}"""
        }
    
    async def send_webhook(self, payload: Dict[str, Any]) -> bool:
        """
        Send payload to Discord webhook
        
        Args:
            payload: Discord webhook payload
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled or not self.webhook_url:
            logger.warning("Discord webhook not enabled or not configured")
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 204:  # Discord webhook success status
                        logger.info("Message sent to Discord webhook successfully")
                        return True
                    else:
                        logger.error(f"Discord webhook returned status {response.status}: {await response.text()}")
                        return False
            
        except Exception as e:
            logger.error(f"Failed to send Discord webhook: {e}")
            return False
    
    async def send_message(self, message: str) -> bool:
        """
        Send simple text message to Discord webhook
        
        Args:
            message: Message to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        # Split long messages if needed (Discord has 2000 char limit)
        if len(message) > 2000:
            chunks = [message[i:i+1900] for i in range(0, len(message), 1900)]
            success = True
            for chunk in chunks:
                chunk_success = await self.send_webhook({"content": chunk})
                success = success and chunk_success
                if len(chunks) > 1:
                    await asyncio.sleep(1)  # Rate limit protection
            return success
        else:
            return await self.send_webhook({"content": message})
    
    async def notify_straddle_result(self, result: Dict[str, Any]) -> bool:
        """
        Send straddle calculation result to Discord webhook
        
        Args:
            result: Straddle calculation result
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        payload = self.format_straddle_message(result)
        return await self.send_webhook(payload)
    
    async def notify_statistics(self, stats: Dict[str, Any]) -> bool:
        """
        Send statistics to Discord webhook
        
        Args:
            stats: Statistics data
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        payload = self.format_statistics_message(stats)
        return await self.send_webhook(payload)
    
    async def notify_multi_timeframe_statistics(self, multi_stats: Dict[str, Any]) -> bool:
        """
        Send multi-timeframe statistics to Discord webhook with Gist link
        
        Args:
            multi_stats: Multi-timeframe statistics result
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            # Format the message
            message_data = self.format_multi_timeframe_message(multi_stats)
            
            if message_data.get("needs_gist") and self.gist_publisher.is_enabled():
                try:
                    # Generate the full report content directly from multi_stats
                    full_report_content = self._generate_full_report_content(multi_stats)
                    
                    if full_report_content:
                        # Create metadata for the Gist
                        timeframes = multi_stats.get('timeframes', {})
                        metadata = {
                            "timeframes_analyzed": len(timeframes),
                            "total_data_points": multi_stats.get('summary', {}).get('total_data_points', 0),
                            "report_length": len(full_report_content)
                        }
                        
                        # Publish to Gist
                        gist_result = await self.gist_publisher.publish_analysis_report(
                            full_report_content,
                            metadata
                        )
                        
                        if gist_result and gist_result.get("status") == "success":
                            # Update the message with the Gist URL
                            content = message_data["content"]
                            content = content.replace(
                                "📋 **Full Analysis:** Creating detailed report...\n🔗 Link will be updated shortly",
                                f"📋 **Full Analysis:** Complete report with all {metadata['timeframes_analyzed']} timeframes\n🔗 {gist_result['url']}"
                            )
                            message_data["content"] = content
                            logger.info(f"Created Gist for multi-timeframe analysis: {gist_result['url']}")
                        else:
                            # Fallback to API endpoint
                            content = message_data["content"]
                            content = content.replace(
                                "📋 **Full Analysis:** Creating detailed report...\n🔗 Link will be updated shortly",
                                "📋 **Full Analysis:** All timeframes available via API\n🔗 `/api/spx-straddle/statistics/multi-timeframe`"
                            )
                            message_data["content"] = content
                            logger.warning("Failed to create Gist, using API endpoint fallback")
                    else:
                        logger.error("Failed to generate full report content for Gist")
                        
                except Exception as e:
                    logger.error(f"Error creating Gist: {e}")
                    # Fallback to API endpoint
                    content = message_data["content"]
                    content = content.replace(
                        "📋 **Full Analysis:** Creating detailed report...\n🔗 Link will be updated shortly",
                        "📋 **Full Analysis:** All timeframes available via API\n🔗 `/api/spx-straddle/statistics/multi-timeframe`"
                    )
                    message_data["content"] = content
            else:
                # No Gist needed or not enabled, use API endpoint
                if "needs_gist" in message_data:
                    content = message_data["content"]
                    content = content.replace(
                        "📋 **Full Analysis:** Creating detailed report...\n🔗 Link will be updated shortly",
                        "📋 **Full Analysis:** All timeframes available via API\n🔗 `/api/spx-straddle/statistics/multi-timeframe`"
                    )
                    message_data["content"] = content
            
            # Send the message
            return await self.send_webhook(message_data)
            
        except Exception as e:
            logger.error(f"Error sending multi-timeframe statistics to Discord: {e}")
            return False
    
    async def notify_daily_timeframe_statistics(self, multi_stats: Dict[str, Any]) -> bool:
        """
        Send daily timeframe statistics (1D-14D) to Discord webhook
        
        Args:
            multi_stats: Multi-timeframe statistics data
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        payload = self.format_daily_timeframe_message(multi_stats)
        return await self.send_webhook(payload)
    
    async def notify_error(self, error: str, context: str = "SPX Straddle") -> bool:
        """
        Send error notification to Discord webhook
        
        Args:
            error: Error message
            context: Context of the error
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        payload = self.format_error_message(error, context)
        return await self.send_webhook(payload)
    
    async def notify_daily_summary(self, straddle_result: Dict[str, Any], stats: Dict[str, Any] = None) -> bool:
        """
        Send daily summary with straddle cost and optional statistics
        
        Args:
            straddle_result: Today's straddle calculation
            stats: Optional statistics data
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            # Send straddle result
            success = await self.notify_straddle_result(straddle_result)
            
            # Send statistics if provided and successful
            if success and stats and stats.get('status') == 'success':
                await asyncio.sleep(1)  # Small delay between messages
                await self.notify_statistics(stats)
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")
            return False
    
    def is_enabled(self) -> bool:
        """Check if Discord webhook notifications are enabled"""
        return self.enabled and bool(self.webhook_url)
    
    def _generate_full_report_content(self, multi_stats: Dict[str, Any]) -> str:
        """
        Generate full markdown report content from multi-timeframe statistics
        
        Args:
            multi_stats: Multi-timeframe statistics data
            
        Returns:
            Markdown formatted report content
        """
        try:
            timeframes = multi_stats.get('timeframes', {})
            summary = multi_stats.get('summary', {})
            
            # Generate formatted report
            et_tz = pytz.timezone('US/Eastern')
            timestamp = datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S ET')
            
            report = f"""# SPX 0DTE Straddle Complete Multi-Timeframe Analysis
Generated: {timestamp}
Total Historical Data: {summary.get('total_data_points', 'N/A')} trading days

## Executive Summary
This comprehensive analysis covers {len(timeframes)} timeframes from daily (1D) to long-term (900D) perspectives, providing insights into SPX 0DTE straddle cost volatility patterns across different time horizons.

## Detailed Timeframe Analysis

"""
            
            # Sort timeframes by period days for logical progression
            sorted_timeframes = sorted(timeframes.items(), key=lambda x: x[1].get('period_days', 0))
            
            for timeframe_key, tf_data in sorted_timeframes:
                period_label = tf_data.get('period_label', timeframe_key)
                period_days = tf_data.get('period_days', 0)
                data_points = tf_data.get('data_points', 0)
                coverage = tf_data.get('coverage_percentage', 0)
                
                # Descriptive stats
                desc_stats = tf_data.get('descriptive_stats', {})
                mean_cost = desc_stats.get('mean', 0)
                median_cost = desc_stats.get('median', 0)
                std_dev = desc_stats.get('std_dev', 0)
                min_cost = desc_stats.get('min', 0)
                max_cost = desc_stats.get('max', 0)
                
                # Trend analysis
                trend_analysis = tf_data.get('trend_analysis', {})
                trend_direction = trend_analysis.get('direction', 'unknown')
                trend_strength = trend_analysis.get('strength', 'unknown')
                
                # Volatility analysis
                vol_analysis = tf_data.get('volatility_analysis', {})
                vol_category = vol_analysis.get('category', 'unknown')
                coefficient_of_variation = vol_analysis.get('coefficient_of_variation', 0)
                
                # Percentiles
                percentiles = tf_data.get('percentiles', {})
                p25 = percentiles.get('25th', 0)
                p75 = percentiles.get('75th', 0)
                p90 = percentiles.get('90th', 0)
                p95 = percentiles.get('95th', 0)
                
                # Format section
                report += f"""### {period_label}
**Data Coverage:** {data_points} data points

**Central Tendency:**
- Mean: ${mean_cost:.2f}
- Median: ${median_cost:.2f}
- Standard Deviation: ${std_dev:.2f}

**Range & Distribution:**
- Minimum: ${min_cost:.2f}
- Maximum: ${max_cost:.2f}
- 25th Percentile: ${p25:.2f}
- 75th Percentile: ${p75:.2f}
- 90th Percentile: ${p90:.2f}
- 95th Percentile: ${p95:.2f}

**Trend Analysis:**
- Direction: {trend_direction.title()}
- Strength: {trend_strength.title()}

**Volatility Profile:**
- Category: {vol_category.title()}
- Coefficient of Variation: {coefficient_of_variation:.1f}%

---

"""
            
            # Add comparative analysis
            report += """## Comparative Analysis

### Volatility Regime Classification
"""
            
            # Group by volatility categories
            vol_categories = {'low': [], 'medium': [], 'high': []}
            for timeframe_key, tf_data in timeframes.items():
                vol_cat = tf_data.get('volatility_analysis', {}).get('category', 'unknown')
                if vol_cat in vol_categories:
                    vol_categories[vol_cat].append((timeframe_key, tf_data))
            
            for vol_cat, timeframe_list in vol_categories.items():
                if timeframe_list:
                    report += f"\n**{vol_cat.title()} Volatility Timeframes:**\n"
                    for tf_key, tf_data in timeframe_list:
                        period_label = tf_data.get('period_label', tf_key)
                        mean_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
                        cv = tf_data.get('volatility_analysis', {}).get('coefficient_of_variation', 0)
                        report += f"- {period_label}: ${mean_cost:.2f} avg (CV: {cv:.1f}%)\n"
            
            # Add trend analysis summary
            report += "\n### Trend Direction Summary\n"
            trend_categories = {'increasing': [], 'decreasing': [], 'stable': []}
            for timeframe_key, tf_data in timeframes.items():
                trend_dir = tf_data.get('trend_analysis', {}).get('direction', 'unknown')
                if trend_dir in trend_categories:
                    trend_categories[trend_dir].append((timeframe_key, tf_data))
            
            for trend_dir, timeframe_list in trend_categories.items():
                if timeframe_list:
                    report += f"\n**{trend_dir.title()} Trend Timeframes:**\n"
                    for tf_key, tf_data in timeframe_list:
                        period_label = tf_data.get('period_label', tf_key)
                        mean_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
                        report += f"- {period_label}: ${mean_cost:.2f} avg\n"
            
            # Add methodology note
            report += f"""

## Methodology
- **Data Source:** Polygon.io SPX and SPXW options data
- **Calculation:** At-the-money (ATM) straddle cost at 9:30 AM ET
- **Strike Selection:** Rounded to nearest $5 increment
- **Timeframes:** {len(timeframes)} periods from 1 day to 900 days
- **Analysis Date:** {timestamp}

## Disclaimer
This analysis is for educational and informational purposes only. Past performance does not guarantee future results. Options trading involves significant risk and may not be suitable for all investors.
"""
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating full report content: {e}")
            return None 