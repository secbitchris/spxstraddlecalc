import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
import aiohttp
import pytz
from dotenv import load_dotenv

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
        Initialize Discord webhook notifier
        
        Args:
            webhook_url: Discord webhook URL (defaults to env var)
        """
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.enabled = os.getenv("DISCORD_ENABLED", "false").lower() == "true"
        
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            self.enabled = False
        
        if self.enabled:
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
        Format multi-timeframe statistics into Discord webhook payload
        
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
            
            # Get key timeframes for summary
            key_periods = ['30d', '90d', '180d', '360d', '720d', '900d']
            available_periods = [p for p in key_periods if p in timeframes]
            
            content = f"""📊 **SPX Straddle Multi-Timeframe Analysis**
*Historical data spanning {len(available_periods)} key timeframes*

"""
            
            # Add timeframe summary
            for period in available_periods:
                tf_data = timeframes[period]
                data_points = tf_data.get('data_points', 0)
                avg_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
                trend = tf_data.get('trend_analysis', {}).get('direction', 'unknown')
                coverage = summary.get('data_coverage', {}).get(period, {}).get('coverage_percentage', 0)
                
                # Trend emoji
                trend_emoji = {
                    'increasing': '📈',
                    'decreasing': '📉', 
                    'stable': '➡️'
                }.get(trend, '❓')
                
                content += f"**{period.upper()}:** {data_points} pts ({coverage:.0f}%) {trend_emoji} ${avg_cost:.2f} avg\n"
            
            # Add key insights
            total_points = summary.get('data_coverage', {}).get('900d', {}).get('data_points', 0)
            recommended = summary.get('recommended_timeframe', '900d')
            
            content += f"""
🎯 **Key Insights:**
• **Total Data Points:** {total_points} trading days
• **Recommended Analysis:** {recommended.upper()}
• **Trend Consistency:** {'Mixed trends across timeframes' if not summary.get('trend_consistency', True) else 'Consistent trends'}

📈 **Recent vs Long-term:**"""
            
            # Compare recent vs long-term
            if '30d' in timeframes and '720d' in timeframes:
                recent_avg = timeframes['30d'].get('descriptive_stats', {}).get('mean', 0)
                longterm_avg = timeframes['720d'].get('descriptive_stats', {}).get('mean', 0)
                change_pct = ((recent_avg - longterm_avg) / longterm_avg * 100) if longterm_avg > 0 else 0
                
                content += f"""
• 30-day avg: ${recent_avg:.2f}
• 720-day avg: ${longterm_avg:.2f}
• Change: {change_pct:+.1f}%"""
            
            # Add volatility insight
            if '360d' in timeframes:
                vol_category = timeframes['360d'].get('volatility_analysis', {}).get('category', 'unknown')
                vol_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(vol_category, '⚪')
                content += f"""

🎢 **Volatility Status:** {vol_emoji} {vol_category.title()}"""
            
            return {"content": content}
            
        except Exception as e:
            logger.error(f"Error formatting multi-timeframe message: {e}")
            return {"content": f"❌ Error formatting multi-timeframe statistics: {str(e)}"}
    
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
        Send multi-timeframe statistics to Discord webhook
        
        Args:
            multi_stats: Multi-timeframe statistics data
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        payload = self.format_multi_timeframe_message(multi_stats)
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