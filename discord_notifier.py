import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
import discord
from discord.ext import commands
import pytz
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class DiscordNotifier:
    """
    Discord notification service for SPX straddle calculations
    
    Sends formatted messages to Discord channels with straddle cost data,
    statistics, and analysis results.
    """
    
    def __init__(self, bot_token: str = None, channel_id: str = None):
        """
        Initialize Discord notifier
        
        Args:
            bot_token: Discord bot token (defaults to env var)
            channel_id: Discord channel ID (defaults to env var)
        """
        self.bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")
        self.channel_id = int(channel_id or os.getenv("DISCORD_CHANNEL_ID", "0"))
        self.enabled = os.getenv("DISCORD_ENABLED", "false").lower() == "true"
        
        # Discord client setup
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.channel = None
        self.connected = False
        
        if not self.bot_token or not self.channel_id:
            logger.warning("Discord bot token or channel ID not configured")
            self.enabled = False
    
    async def initialize(self):
        """Initialize Discord connection"""
        if not self.enabled:
            logger.info("Discord notifications disabled")
            return
        
        try:
            await self.client.login(self.bot_token)
            logger.info("Discord client logged in successfully")
            
            # Get the channel
            self.channel = self.client.get_channel(self.channel_id)
            if not self.channel:
                logger.error(f"Could not find Discord channel with ID: {self.channel_id}")
                self.enabled = False
                return
            
            self.connected = True
            logger.info(f"Discord notifier initialized for channel: {self.channel.name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Discord client: {e}")
            self.enabled = False
    
    async def close(self):
        """Close Discord connection"""
        if self.client and not self.client.is_closed():
            await self.client.close()
            logger.info("Discord client closed")
    
    def format_straddle_message(self, result: Dict[str, Any]) -> str:
        """
        Format straddle calculation result into Discord message
        
        Args:
            result: Straddle calculation result
            
        Returns:
            Formatted Discord message string
        """
        try:
            et_tz = pytz.timezone('US/Eastern')
            timestamp = datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S ET')
            
            if 'error' in result:
                return f"""🚨 **SPX Straddle Calculation Error**
```
Error: {result['error']}
Time: {timestamp}
```"""
            
            # Success message
            straddle_cost = result.get('straddle_cost', 0)
            spx_price = result.get('spx_price_930am', 0)
            atm_strike = result.get('atm_strike', 0)
            call_price = result.get('call_price_931am', 0)
            put_price = result.get('put_price_931am', 0)
            calc_date = result.get('calculation_date', 'Unknown')
            
            # Create formatted message with emojis and styling
            message = f"""📊 **SPX 0DTE Straddle Cost - {calc_date}**

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
                    message += "\n💡 **Analysis:** Low cost straddle - potential opportunity"
                elif straddle_cost > 60:
                    message += "\n⚠️ **Analysis:** High cost straddle - elevated volatility expected"
                else:
                    message += "\n📊 **Analysis:** Moderate cost straddle"
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting straddle message: {e}")
            return f"❌ Error formatting straddle data: {str(e)}"
    
    def format_statistics_message(self, stats: Dict[str, Any]) -> str:
        """
        Format statistics into Discord message
        
        Args:
            stats: Statistics calculation result
            
        Returns:
            Formatted Discord message string
        """
        try:
            if stats.get('status') != 'success':
                return f"❌ **Statistics Error:** {stats.get('error_message', 'Unknown error')}"
            
            desc_stats = stats.get('descriptive_stats', {})
            trend = stats.get('trend_analysis', {})
            volatility = stats.get('volatility_analysis', {})
            recent = stats.get('recent_comparison', {})
            period = stats.get('period_days', 30)
            
            message = f"""📈 **SPX Straddle Statistics ({period} days)**

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
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting statistics message: {e}")
            return f"❌ Error formatting statistics: {str(e)}"
    
    def format_error_message(self, error: str, context: str = "SPX Straddle") -> str:
        """
        Format error message for Discord
        
        Args:
            error: Error message
            context: Context of the error
            
        Returns:
            Formatted error message
        """
        et_tz = pytz.timezone('US/Eastern')
        timestamp = datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S ET')
        
        return f"""🚨 **{context} Error**
```
{error}
```
⏰ **Time:** {timestamp}"""
    
    async def send_message(self, message: str) -> bool:
        """
        Send message to Discord channel
        
        Args:
            message: Message to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled or not self.connected or not self.channel:
            logger.warning("Discord not enabled or not connected")
            return False
        
        try:
            # Split long messages if needed (Discord has 2000 char limit)
            if len(message) > 2000:
                chunks = [message[i:i+1900] for i in range(0, len(message), 1900)]
                for chunk in chunks:
                    await self.channel.send(chunk)
            else:
                await self.channel.send(message)
            
            logger.info("Message sent to Discord successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False
    
    async def notify_straddle_result(self, result: Dict[str, Any]) -> bool:
        """
        Send straddle calculation result to Discord
        
        Args:
            result: Straddle calculation result
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        message = self.format_straddle_message(result)
        return await self.send_message(message)
    
    async def notify_statistics(self, stats: Dict[str, Any]) -> bool:
        """
        Send statistics to Discord
        
        Args:
            stats: Statistics data
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        message = self.format_statistics_message(stats)
        return await self.send_message(message)
    
    async def notify_error(self, error: str, context: str = "SPX Straddle") -> bool:
        """
        Send error notification to Discord
        
        Args:
            error: Error message
            context: Context of the error
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        message = self.format_error_message(error, context)
        return await self.send_message(message)
    
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
        """Check if Discord notifications are enabled and connected"""
        return self.enabled and self.connected
    
    def get_status(self) -> Dict[str, Any]:
        """Get Discord notifier status"""
        return {
            'enabled': self.enabled,
            'connected': self.connected,
            'channel_id': self.channel_id,
            'channel_name': self.channel.name if self.channel else None,
            'bot_configured': bool(self.bot_token)
        } 