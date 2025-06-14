import asyncio
import logging
from datetime import datetime, time
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
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

class SPXStraddleScheduler:
    """
    Scheduler for automated SPX straddle calculations with Discord notifications
    
    Handles:
    - Daily straddle calculations at market open
    - Discord notifications for results
    - Weekly data cleanup
    - Error handling and recovery
    """
    
    def __init__(self):
        """Initialize the scheduler with configuration from environment variables"""
        self.enable_scheduler = os.getenv("ENABLE_SCHEDULER", "false").lower() == "true"
        
        # Parse CALCULATION_TIME with robust error handling for comments
        calc_time_str = os.getenv("CALCULATION_TIME", "09:47:20")
        self.calculation_time = calc_time_str.split('#')[0].strip()
        
        # Parse CLEANUP_DAY with robust error handling for comments
        cleanup_day_str = os.getenv("CLEANUP_DAY", "sunday")
        self.cleanup_day = cleanup_day_str.split('#')[0].strip().lower()
        
        # Parse CLEANUP_TIME with robust error handling for comments
        cleanup_time_str = os.getenv("CLEANUP_TIME", "02:00")
        self.cleanup_time = cleanup_time_str.split('#')[0].strip()
        
        # Parse KEEP_DAYS with robust error handling for comments
        keep_days_str = os.getenv("KEEP_DAYS", "90")
        # Strip comments and whitespace
        keep_days_str = keep_days_str.split('#')[0].strip()
        self.keep_days = int(keep_days_str)
        
        self.scheduler = AsyncIOScheduler()
        self.running = False
        self.calculator = None
        self.discord_notifier = None
        
        logger.info(f"Scheduler configuration:")
        logger.info(f"  - Daily calculation: {self.calculation_time} ET")
        logger.info(f"  - Weekly cleanup: {self.cleanup_day} {self.cleanup_time} ET")
        logger.info(f"  - Data retention: {self.keep_days} days")
        logger.info(f"  - Scheduler enabled: {self.enable_scheduler}")
    
    async def initialize(self):
        """Initialize calculator and Discord notifier"""
        try:
            # Initialize calculator
            polygon_api_key = os.getenv("POLYGON_API_KEY")
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            
            if not polygon_api_key:
                raise ValueError("POLYGON_API_KEY environment variable is required")
            
            self.calculator = SPXStraddleCalculator(polygon_api_key, redis_url)
            await self.calculator.initialize()
            logger.info("SPX Straddle Calculator initialized")
            
            # Initialize Discord notifier
            self.discord_notifier = DiscordNotifier()
            await self.discord_notifier.initialize()
            
            if self.discord_notifier.is_enabled():
                logger.info("Discord notifier initialized and connected")
            else:
                logger.info("Discord notifier disabled or not configured")
            
        except Exception as e:
            logger.error(f"Failed to initialize scheduler components: {e}")
            raise
    
    async def daily_calculation(self):
        """
        Perform daily straddle calculation and send Discord notification
        
        This is the main scheduled task that runs every weekday morning.
        """
        try:
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            
            # Only run on weekdays (Monday=0, Sunday=6)
            if now_et.weekday() >= 5:
                logger.info("Skipping calculation - weekend")
                return
            
            logger.info("🚀 Starting scheduled daily straddle calculation")
            
            # Perform calculation
            result = await self.calculator.calculate_spx_straddle_cost()
            
            if 'error' in result:
                error_msg = f"Scheduled calculation failed: {result['error']}"
                logger.error(error_msg)
                
                # Send error notification to Discord
                if self.discord_notifier and self.discord_notifier.is_enabled():
                    await self.discord_notifier.notify_error(error_msg, "Daily Calculation")
                
            else:
                straddle_cost = result.get('straddle_cost', 0)
                logger.info(f"✅ Scheduled calculation successful! Straddle cost: ${straddle_cost:.2f}")
                
                # Send success notification to Discord with statistics
                if self.discord_notifier and self.discord_notifier.is_enabled():
                    try:
                        # Get 30-day statistics for context
                        stats = await self.calculator.calculate_spx_straddle_statistics(30)
                        await self.discord_notifier.notify_daily_summary(result, stats)
                        logger.info("📱 Discord notification sent successfully")
                    except Exception as discord_error:
                        logger.error(f"Failed to send Discord notification: {discord_error}")
                        # Still try to send just the basic result
                        await self.discord_notifier.notify_straddle_result(result)
                
        except Exception as e:
            error_msg = f"Error in scheduled daily calculation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Send error notification to Discord
            if self.discord_notifier and self.discord_notifier.is_enabled():
                try:
                    await self.discord_notifier.notify_error(error_msg, "Daily Calculation")
                except Exception as discord_error:
                    logger.error(f"Failed to send error notification to Discord: {discord_error}")
    
    async def weekly_cleanup(self):
        """
        Perform weekly data cleanup
        
        Removes old straddle data to keep storage manageable.
        """
        try:
            logger.info("🧹 Starting weekly data cleanup")
            
            await self.calculator.cleanup_old_data(self.keep_days)
            
            cleanup_msg = f"Weekly cleanup completed - keeping {self.keep_days} days of data"
            logger.info(cleanup_msg)
            
            # Send cleanup notification to Discord (optional)
            if self.discord_notifier and self.discord_notifier.is_enabled():
                try:
                    message = f"🧹 **Weekly Cleanup Complete**\n\nRemoved data older than {self.keep_days} days.\nSystem maintenance completed successfully."
                    await self.discord_notifier.send_message(message)
                except Exception as discord_error:
                    logger.error(f"Failed to send cleanup notification to Discord: {discord_error}")
                    
        except Exception as e:
            error_msg = f"Error in weekly cleanup: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Send error notification to Discord
            if self.discord_notifier and self.discord_notifier.is_enabled():
                try:
                    await self.discord_notifier.notify_error(error_msg, "Weekly Cleanup")
                except Exception as discord_error:
                    logger.error(f"Failed to send cleanup error notification to Discord: {discord_error}")
    
    async def test_calculation(self):
        """
        Test calculation for debugging purposes
        
        Can be called manually or scheduled for testing.
        """
        try:
            logger.info("🧪 Running test calculation")
            
            result = await self.calculator.calculate_spx_straddle_cost()
            
            if 'error' in result:
                logger.error(f"Test calculation failed: {result['error']}")
            else:
                logger.info(f"Test calculation successful: ${result.get('straddle_cost', 0):.2f}")
                
                # Send test notification to Discord
                if self.discord_notifier and self.discord_notifier.is_enabled():
                    test_result = result.copy()
                    test_result['calculation_date'] = f"{test_result.get('calculation_date', 'Unknown')} (TEST)"
                    await self.discord_notifier.notify_straddle_result(test_result)
                    
        except Exception as e:
            logger.error(f"Error in test calculation: {e}", exc_info=True)
    
    def schedule_jobs(self):
        """Configure and schedule all automated jobs"""
        if not self.enable_scheduler:
            logger.info("Scheduler disabled by configuration")
            return
        
        try:
            # Parse calculation time (supports HH:MM or HH:MM:SS format)
            # Strip comments and whitespace
            calc_time_clean = self.calculation_time.split('#')[0].strip()
            time_parts = calc_time_clean.split(':')
            calc_hour = int(time_parts[0])
            calc_minute = int(time_parts[1])
            calc_second = int(time_parts[2]) if len(time_parts) > 2 else 0
            
            # Daily calculation at specified time (weekdays only)
            self.scheduler.add_job(
                self.daily_calculation,
                CronTrigger(
                    hour=calc_hour,
                    minute=calc_minute,
                    second=calc_second,
                    day_of_week='mon-fri',  # Monday to Friday
                    timezone='US/Eastern'
                ),
                id='daily_calculation',
                name='Daily SPX Straddle Calculation',
                max_instances=1,
                coalesce=True
            )
            
            # Parse cleanup time (supports HH:MM or HH:MM:SS format)
            # Strip comments and whitespace
            cleanup_time_clean = self.cleanup_time.split('#')[0].strip()
            cleanup_time_parts = cleanup_time_clean.split(':')
            cleanup_hour = int(cleanup_time_parts[0])
            cleanup_minute = int(cleanup_time_parts[1])
            cleanup_second = int(cleanup_time_parts[2]) if len(cleanup_time_parts) > 2 else 0
            
            # Weekly cleanup
            cleanup_day_map = {
                'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
                'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
            }
            
            self.scheduler.add_job(
                self.weekly_cleanup,
                CronTrigger(
                    hour=cleanup_hour,
                    minute=cleanup_minute,
                    second=cleanup_second,
                    day_of_week=cleanup_day_map.get(self.cleanup_day, 'sun'),
                    timezone='US/Eastern'
                ),
                id='weekly_cleanup',
                name='Weekly Data Cleanup',
                max_instances=1,
                coalesce=True
            )
            
            logger.info("Scheduled jobs configured:")
            logger.info(f"  - Daily calculation: {self.calculation_time} ET (weekdays)")
            logger.info(f"  - Weekly cleanup: {self.cleanup_day.title()} {self.cleanup_time} ET")
            
        except Exception as e:
            logger.error(f"Error scheduling jobs: {e}")
            raise
    
    async def start(self):
        """Start the scheduler"""
        try:
            await self.initialize()
            self.schedule_jobs()
            
            if self.enable_scheduler:
                self.scheduler.start()
                self.running = True
                logger.info("🚀 SPX Straddle Scheduler started")
                
                # Send startup notification to Discord
                if self.discord_notifier and self.discord_notifier.is_enabled():
                    try:
                        startup_msg = f"""🚀 **SPX Straddle Scheduler Started**

**Configuration:**
• Daily calculation: {self.calculation_time} ET (weekdays)
• Weekly cleanup: {self.cleanup_day.title()} {self.cleanup_time} ET
• Data retention: {self.keep_days} days

Scheduler is now running and will automatically calculate SPX straddle costs each trading day."""
                        await self.discord_notifier.send_message(startup_msg)
                    except Exception as discord_error:
                        logger.error(f"Failed to send startup notification: {discord_error}")
            else:
                logger.info("Scheduler initialized but not started (disabled by configuration)")
                
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise
    
    async def stop(self):
        """Stop the scheduler"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.info("Scheduler stopped")
            
            self.running = False
            
            # Send shutdown notification to Discord
            if self.discord_notifier and self.discord_notifier.is_enabled():
                try:
                    shutdown_msg = "🛑 **SPX Straddle Scheduler Stopped**\n\nScheduled calculations have been disabled."
                    await self.discord_notifier.send_message(shutdown_msg)
                except Exception as discord_error:
                    logger.error(f"Failed to send shutdown notification: {discord_error}")
            
            # Clean up connections
            if self.calculator:
                await self.calculator.close()
            if self.discord_notifier:
                await self.discord_notifier.close()
                
            logger.info("Scheduler shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")
    
    async def run_forever(self):
        """Run the scheduler indefinitely"""
        await self.start()
        
        if not self.enable_scheduler:
            logger.info("Scheduler disabled - exiting")
            return
        
        try:
            # Keep the scheduler running
            while self.running:
                await asyncio.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Unexpected error in scheduler loop: {e}")
        finally:
            await self.stop()
    
    def get_status(self):
        """Get scheduler status"""
        jobs = []
        if self.scheduler:
            for job in self.scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger)
                })
        
        return {
            'running': self.running,
            'enabled': self.enable_scheduler,
            'calculator_initialized': self.calculator is not None,
            'discord_enabled': self.discord_notifier.is_enabled() if self.discord_notifier else False,
            'jobs': jobs,
            'configuration': {
                'calculation_time': self.calculation_time,
                'cleanup_day': self.cleanup_day,
                'cleanup_time': self.cleanup_time,
                'keep_days': self.keep_days
            }
        }

async def main():
    """Main function to run the scheduler"""
    scheduler = SPXStraddleScheduler()
    
    try:
        await scheduler.run_forever()
    except Exception as e:
        logger.error(f"Fatal error in scheduler: {e}", exc_info=True)
    finally:
        logger.info("Scheduler main function exiting")

if __name__ == "__main__":
    asyncio.run(main()) 