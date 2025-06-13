#!/usr/bin/env python3
"""
Historical SPX Straddle Data Backfill Script

This script fetches historical SPX straddle costs for past trading days
and stores them in Redis for statistical analysis.

Features:
- Fetches SPX index prices at 9:30 AM for historical dates
- Calculates ATM strikes for each date
- Fetches historical SPX options prices at 9:31 AM
- Calculates and stores straddle costs
- Supports date ranges (1-2 years back)
- Handles market holidays and weekends
- Progress tracking and error handling
- Batch processing for efficiency
"""

import asyncio
import os
import json
import pytz
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging
from spx_calculator import SPXStraddleCalculator
from discord_notifier import DiscordNotifier

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class BackfillProgress:
    """Track backfill progress"""
    total_days: int
    processed_days: int
    successful_days: int
    failed_days: int
    skipped_days: int
    start_time: datetime
    
    @property
    def completion_percentage(self) -> float:
        return (self.processed_days / self.total_days) * 100 if self.total_days > 0 else 0
    
    @property
    def success_rate(self) -> float:
        return (self.successful_days / self.processed_days) * 100 if self.processed_days > 0 else 0

class HistoricalBackfill:
    """Historical SPX straddle data backfill manager"""
    
    def __init__(self, polygon_api_key: str, redis_url: str = None):
        self.polygon_api_key = polygon_api_key
        self.redis_url = redis_url
        self.calculator = None
        self.notifier = None
        self.et_tz = pytz.timezone('US/Eastern')
        
    async def initialize(self):
        """Initialize calculator and notifier"""
        # Use environment variable for Redis URL if not provided
        if self.redis_url is None:
            self.redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
        
        self.calculator = SPXStraddleCalculator(self.polygon_api_key, self.redis_url)
        await self.calculator.initialize()
        
        # Initialize Discord notifier if available
        discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
        if discord_webhook and os.getenv('DISCORD_ENABLED', 'false').lower() == 'true':
            self.notifier = DiscordNotifier(discord_webhook)
            await self.notifier.initialize()
        
        logger.info("Historical backfill initialized")
    
    async def close(self):
        """Clean up resources"""
        if self.calculator:
            await self.calculator.close()
        if self.notifier:
            await self.notifier.close()
    
    def get_trading_days(self, start_date: date, end_date: date) -> List[date]:
        """
        Generate list of trading days between start and end dates
        Excludes weekends and major US holidays
        """
        trading_days = []
        current_date = start_date
        
        # Major US market holidays (approximate - doesn't include all)
        holidays_2024 = {
            date(2024, 1, 1),   # New Year's Day
            date(2024, 1, 15),  # MLK Day
            date(2024, 2, 19),  # Presidents Day
            date(2024, 3, 29),  # Good Friday
            date(2024, 5, 27),  # Memorial Day
            date(2024, 6, 19),  # Juneteenth
            date(2024, 7, 4),   # Independence Day
            date(2024, 9, 2),   # Labor Day
            date(2024, 11, 28), # Thanksgiving
            date(2024, 12, 25), # Christmas
        }
        
        holidays_2025 = {
            date(2025, 1, 1),   # New Year's Day
            date(2025, 1, 20),  # MLK Day
            date(2025, 2, 17),  # Presidents Day
            date(2025, 4, 18),  # Good Friday
            date(2025, 5, 26),  # Memorial Day
            date(2025, 6, 19),  # Juneteenth
            date(2025, 7, 4),   # Independence Day
            date(2025, 9, 1),   # Labor Day
            date(2025, 11, 27), # Thanksgiving
            date(2025, 12, 25), # Christmas
        }
        
        all_holidays = holidays_2024.union(holidays_2025)
        
        while current_date <= end_date:
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() < 5 and current_date not in all_holidays:
                trading_days.append(current_date)
            current_date += timedelta(days=1)
        
        return trading_days
    
    async def check_existing_data(self, target_date: date) -> bool:
        """Check if data already exists for a given date"""
        if not self.calculator.redis:
            return False
        
        redis_key = f'spx_straddle_cost_{target_date.strftime("%Y%m%d")}'
        existing_data = self.calculator.redis.get(redis_key)
        
        if existing_data:
            try:
                data = json.loads(existing_data)
                return data.get('calculation_status') == 'available'
            except:
                return False
        
        return False
    
    async def backfill_single_date(self, target_date: date) -> Dict[str, Any]:
        """
        Backfill straddle data for a single date
        
        Returns:
            Dict with success status and data or error information
        """
        try:
            logger.info(f"Processing {target_date}")
            
            # Check if data already exists
            if await self.check_existing_data(target_date):
                logger.info(f"Data already exists for {target_date}, skipping")
                return {
                    'status': 'skipped',
                    'date': target_date.isoformat(),
                    'reason': 'Data already exists'
                }
            
            # Calculate straddle cost for the target date
            result = await self.calculator.calculate_spx_straddle_cost(target_date)
            
            if 'error' in result:
                logger.warning(f"Failed to calculate straddle for {target_date}: {result['error']}")
                return {
                    'status': 'failed',
                    'date': target_date.isoformat(),
                    'error': result['error']
                }
            
            logger.info(f"Successfully calculated straddle for {target_date}: ${result['straddle_cost']:.2f}")
            return {
                'status': 'success',
                'date': target_date.isoformat(),
                'data': result
            }
            
        except Exception as e:
            logger.error(f"Error processing {target_date}: {e}")
            return {
                'status': 'failed',
                'date': target_date.isoformat(),
                'error': str(e)
            }
    
    async def backfill_date_range(
        self, 
        start_date: date, 
        end_date: date,
        batch_size: int = 10,
        delay_between_batches: float = 1.0
    ) -> Dict[str, Any]:
        """
        Backfill straddle data for a date range
        
        Args:
            start_date: Start date for backfill
            end_date: End date for backfill
            batch_size: Number of dates to process in parallel
            delay_between_batches: Delay between batches (seconds)
            
        Returns:
            Dict with backfill results and statistics
        """
        logger.info(f"Starting backfill from {start_date} to {end_date}")
        
        # Get trading days
        trading_days = self.get_trading_days(start_date, end_date)
        logger.info(f"Found {len(trading_days)} trading days to process")
        
        if not trading_days:
            return {
                'status': 'error',
                'error': 'No trading days found in the specified range'
            }
        
        # Initialize progress tracking
        progress = BackfillProgress(
            total_days=len(trading_days),
            processed_days=0,
            successful_days=0,
            failed_days=0,
            skipped_days=0,
            start_time=datetime.now(self.et_tz)
        )
        
        results = []
        
        # Process in batches
        for i in range(0, len(trading_days), batch_size):
            batch = trading_days[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(trading_days) + batch_size - 1)//batch_size}")
            
            # Process batch in parallel
            batch_tasks = [self.backfill_single_date(date) for date in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Update progress
            for result in batch_results:
                if isinstance(result, Exception):
                    progress.failed_days += 1
                    results.append({
                        'status': 'failed',
                        'error': str(result)
                    })
                else:
                    results.append(result)
                    if result['status'] == 'success':
                        progress.successful_days += 1
                    elif result['status'] == 'failed':
                        progress.failed_days += 1
                    elif result['status'] == 'skipped':
                        progress.skipped_days += 1
                
                progress.processed_days += 1
            
            # Log progress
            logger.info(f"Progress: {progress.completion_percentage:.1f}% "
                       f"({progress.processed_days}/{progress.total_days}) - "
                       f"Success: {progress.successful_days}, "
                       f"Failed: {progress.failed_days}, "
                       f"Skipped: {progress.skipped_days}")
            
            # Delay between batches to avoid rate limiting
            if i + batch_size < len(trading_days):
                await asyncio.sleep(delay_between_batches)
        
        # Calculate final statistics
        end_time = datetime.now(self.et_tz)
        duration = end_time - progress.start_time
        
        summary = {
            'status': 'completed',
            'summary': {
                'total_days': progress.total_days,
                'processed_days': progress.processed_days,
                'successful_days': progress.successful_days,
                'failed_days': progress.failed_days,
                'skipped_days': progress.skipped_days,
                'success_rate': progress.success_rate,
                'duration_seconds': duration.total_seconds(),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'results': results
        }
        
        logger.info(f"Backfill completed! Success rate: {progress.success_rate:.1f}% "
                   f"({progress.successful_days}/{progress.processed_days})")
        
        # Send Discord notification if available
        if self.notifier and self.notifier.is_enabled():
            await self.send_backfill_notification(summary)
        
        return summary
    
    async def send_backfill_notification(self, summary: Dict[str, Any]):
        """Send Discord notification about backfill completion"""
        try:
            stats = summary['summary']
            
            embed = {
                "title": "📊 Historical Backfill Completed",
                "color": 0x00ff00 if stats['success_rate'] > 80 else 0xff9900,
                "fields": [
                    {
                        "name": "📅 Date Range",
                        "value": f"{stats['start_date']} to {stats['end_date']}",
                        "inline": False
                    },
                    {
                        "name": "📈 Results",
                        "value": f"✅ Success: {stats['successful_days']}\n"
                                f"❌ Failed: {stats['failed_days']}\n"
                                f"⏭️ Skipped: {stats['skipped_days']}",
                        "inline": True
                    },
                    {
                        "name": "📊 Statistics",
                        "value": f"Success Rate: {stats['success_rate']:.1f}%\n"
                                f"Duration: {stats['duration_seconds']:.0f}s",
                        "inline": True
                    }
                ],
                "timestamp": datetime.now(self.et_tz).isoformat()
            }
            
            await self.notifier.send_message_with_embed(embed)
            
        except Exception as e:
            logger.error(f"Failed to send backfill notification: {e}")

async def main():
    """Main function for running historical backfill"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SPX Straddle Historical Backfill')
    parser.add_argument('--start-date', type=str, required=True, 
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, 
                       help='End date (YYYY-MM-DD), defaults to yesterday')
    parser.add_argument('--days', type=int, 
                       help='Number of days back from today (alternative to start-date)')
    parser.add_argument('--batch-size', type=int, default=5,
                       help='Batch size for parallel processing (default: 5)')
    parser.add_argument('--delay', type=float, default=2.0,
                       help='Delay between batches in seconds (default: 2.0)')
    
    args = parser.parse_args()
    
    # Get API key
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        logger.error("POLYGON_API_KEY environment variable not set")
        return
    
    # Parse dates
    et_tz = pytz.timezone('US/Eastern')
    today = datetime.now(et_tz).date()
    
    if args.days:
        start_date = today - timedelta(days=args.days)
        end_date = today - timedelta(days=1)  # Yesterday
    else:
        try:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        except ValueError:
            logger.error("Invalid start date format. Use YYYY-MM-DD")
            return
        
        if args.end_date:
            try:
                end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
            except ValueError:
                logger.error("Invalid end date format. Use YYYY-MM-DD")
                return
        else:
            end_date = today - timedelta(days=1)  # Yesterday
    
    # Validate date range
    if start_date >= end_date:
        logger.error("Start date must be before end date")
        return
    
    if end_date >= today:
        logger.error("End date must be before today")
        return
    
    logger.info(f"Backfill configuration:")
    logger.info(f"  Date range: {start_date} to {end_date}")
    logger.info(f"  Batch size: {args.batch_size}")
    logger.info(f"  Delay between batches: {args.delay}s")
    
    # Initialize and run backfill
    backfill = HistoricalBackfill(api_key)
    
    try:
        await backfill.initialize()
        result = await backfill.backfill_date_range(
            start_date=start_date,
            end_date=end_date,
            batch_size=args.batch_size,
            delay_between_batches=args.delay
        )
        
        # Print summary
        print("\n" + "="*60)
        print("BACKFILL SUMMARY")
        print("="*60)
        stats = result['summary']
        print(f"Date Range: {stats['start_date']} to {stats['end_date']}")
        print(f"Total Days: {stats['total_days']}")
        print(f"Successful: {stats['successful_days']}")
        print(f"Failed: {stats['failed_days']}")
        print(f"Skipped: {stats['skipped_days']}")
        print(f"Success Rate: {stats['success_rate']:.1f}%")
        print(f"Duration: {stats['duration_seconds']:.0f} seconds")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
    finally:
        await backfill.close()

if __name__ == "__main__":
    asyncio.run(main()) 