import asyncio
import logging
from datetime import date, datetime
from spx_calculator import SPXStraddleCalculator
from discord_notifier import DiscordNotifier
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Example usage of the SPX Straddle Calculator with Discord integration"""
    
    # Initialize calculator
    polygon_api_key = os.getenv("POLYGON_API_KEY")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    if not polygon_api_key:
        logger.error("POLYGON_API_KEY environment variable is required")
        return
    
    calculator = SPXStraddleCalculator(polygon_api_key, redis_url)
    discord_notifier = DiscordNotifier()
    
    try:
        # Initialize connections
        await calculator.initialize()
        await discord_notifier.initialize()
        logger.info("✅ Calculator and Discord notifier initialized successfully")
        
        print("\n" + "="*60)
        print("🚀 SPX 0DTE STRADDLE CALCULATOR - EXAMPLE USAGE")
        print("="*60)
        
        # Example 1: Calculate today's straddle cost
        print("\n📊 EXAMPLE 1: Calculating Today's Straddle Cost")
        print("-" * 50)
        
        result = await calculator.calculate_spx_straddle_cost()
        
        if 'error' in result:
            logger.error(f"❌ Calculation failed: {result['error']}")
            print(f"Error: {result['error']}")
        else:
            logger.info("✅ Calculation successful!")
            print(f"✅ Calculation successful!")
            print(f"📈 SPX Price @ 9:30 AM: ${result['spx_price_930am']:.2f}")
            print(f"🎯 ATM Strike: {result['atm_strike']}")
            print(f"📞 Call Price @ 9:31 AM: ${result['call_price_931am']:.2f}")
            print(f"📉 Put Price @ 9:31 AM: ${result['put_price_931am']:.2f}")
            print(f"💰 Total Straddle Cost: ${result['straddle_cost']:.2f}")
            
            # Send to Discord if enabled
            if discord_notifier.is_enabled():
                print("\n📱 Sending notification to Discord...")
                discord_success = await discord_notifier.notify_straddle_result(result)
                if discord_success:
                    print("✅ Discord notification sent successfully")
                else:
                    print("❌ Failed to send Discord notification")
        
        # Example 2: Get current straddle data
        print("\n📋 EXAMPLE 2: Getting Current Straddle Data")
        print("-" * 50)
        
        current_data = await calculator.get_spx_straddle_cost()
        print(f"Status: {current_data.get('calculation_status')}")
        if current_data.get('calculation_status') == 'available':
            print(f"Last calculation: {current_data.get('last_calculation_date')}")
            print(f"Straddle cost: ${current_data.get('straddle_cost', 0):.2f}")
        
        # Example 3: Get historical data
        print("\n📈 EXAMPLE 3: Getting Historical Data (30 days)")
        print("-" * 50)
        
        history = await calculator.get_spx_straddle_history(30)
        if history['status'] == 'success':
            print(f"✅ Retrieved {history['count']} historical records")
            print(f"📅 Date range: {history['date_range']['start']} to {history['date_range']['end']}")
            
            # Show last 5 records
            if history['data']:
                print("\n📊 Last 5 records:")
                for record in history['data'][-5:]:
                    date_str = record.get('date', 'N/A')
                    cost = record.get('straddle_cost', 0)
                    print(f"  {date_str}: ${cost:.2f}")
        else:
            print(f"❌ Failed to get history: {history.get('error_message')}")
        
        # Example 4: Calculate statistics
        print("\n📊 EXAMPLE 4: Calculating Statistics (30 days)")
        print("-" * 50)
        
        stats = await calculator.calculate_spx_straddle_statistics(30)
        if stats['status'] == 'success':
            desc_stats = stats['descriptive_stats']
            trend = stats['trend_analysis']
            volatility = stats['volatility_analysis']
            recent = stats['recent_comparison']
            
            print(f"📈 Average cost: ${desc_stats['mean']:.2f}")
            print(f"📊 Median cost: ${desc_stats['median']:.2f}")
            print(f"📉 Min cost: ${desc_stats['min']:.2f}")
            print(f"📈 Max cost: ${desc_stats['max']:.2f}")
            print(f"📏 Standard deviation: ${desc_stats['std_dev']:.2f}")
            print(f"📈 Trend: {trend['direction']} (slope: {trend['slope']:.4f})")
            print(f"🎢 Volatility: {volatility['category']} ({volatility['coefficient_of_variation']:.1f}%)")
            print(f"🔄 Recent 7-day avg: ${recent['recent_7day_avg']:.2f} ({recent['percentage_change']:+.1f}%)")
            
            # Send statistics to Discord if enabled
            if discord_notifier.is_enabled():
                print("\n📱 Sending statistics to Discord...")
                discord_success = await discord_notifier.notify_statistics(stats)
                if discord_success:
                    print("✅ Discord statistics sent successfully")
                else:
                    print("❌ Failed to send Discord statistics")
        else:
            print(f"❌ Failed to calculate statistics: {stats.get('error_message')}")
        
        # Example 5: Test Discord functionality
        if discord_notifier.is_enabled():
            print("\n🧪 EXAMPLE 5: Testing Discord Webhook Integration")
            print("-" * 50)
            
            test_message = "🧪 **Test Message from SPX Straddle Calculator**\n\nThis is a test to verify Discord webhook integration is working correctly!"
            discord_success = await discord_notifier.send_message(test_message)
            if discord_success:
                print("✅ Discord webhook test message sent successfully")
            else:
                print("❌ Failed to send Discord webhook test message")
        else:
            print("\n🔇 EXAMPLE 5: Discord Webhook Integration")
            print("-" * 50)
            print("Discord webhook notifications are disabled or not configured")
            print("To enable Discord webhooks:")
            print("1. Go to your Discord server")
            print("2. Right-click the channel → Edit Channel → Integrations → Webhooks")
            print("3. Create a new webhook and copy the URL")
            print("4. Set DISCORD_WEBHOOK_URL environment variable")
            print("5. Set DISCORD_ENABLED=true")
            print("6. Much simpler than bot tokens - no permissions needed!")
        
        # Example 6: System status
        print("\n🔍 EXAMPLE 6: System Status")
        print("-" * 50)
        
        print(f"Calculator initialized: ✅")
        print(f"Redis connected: {'✅' if calculator.redis else '❌'}")
        print(f"Discord enabled: {'✅' if discord_notifier.is_enabled() else '❌'}")
        if discord_notifier.is_enabled():
            discord_status = discord_notifier.get_status()
            print(f"Discord webhook configured: {'✅' if discord_status['webhook_configured'] else '❌'}")
            if discord_status['webhook_configured']:
                print(f"Discord type: {discord_status['type']}")
        
        # Example 7: Clean up old data (demonstration)
        print("\n🧹 EXAMPLE 7: Data Cleanup (keeping 90 days)")
        print("-" * 50)
        
        await calculator.cleanup_old_data(90)
        print("✅ Cleanup completed")
        
        print("\n" + "="*60)
        print("🎉 ALL EXAMPLES COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\n📚 Next Steps:")
        print("1. 🌐 Start the API server: python api_server.py")
        print("2. 📅 Start the scheduler: python scheduler.py")
        print("3. 🔗 Visit the dashboard: http://localhost:8000/api/spx-straddle/dashboard")
        print("4. 📖 View API docs: http://localhost:8000/docs")
        print("5. 🐳 Use Docker: docker-compose up")
        
    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        
        # Send error to Discord if possible
        if discord_notifier and discord_notifier.is_enabled():
            try:
                await discord_notifier.notify_error(str(e), "Example Usage")
            except:
                pass  # Don't fail on Discord error notification
    
    finally:
        # Clean up connections
        if calculator:
            await calculator.close()
        if discord_notifier:
            await discord_notifier.close()
        logger.info("🔚 Example usage completed - connections closed")

if __name__ == "__main__":
    asyncio.run(main()) 