#!/usr/bin/env python3
"""
Generate animated activity log SVG with real GitHub data
"""

import os
import requests
from datetime import datetime
from github import Github

# Настройки
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME', 'keelbismark')
OUTPUT_FILE = 'assets/activity-log.svg'
MAX_EVENTS = 7

# Цвета для разных типов событий
EVENT_COLORS = {
    'PushEvent': ('#10b981', 'SUCCESS'),
    'PullRequestEvent': ('#60a5fa', 'MERGE'),
    'IssuesEvent': ('#fbbf24', 'ISSUE'),
    'CreateEvent': ('#a855f7', 'CREATE'),
    'DeleteEvent': ('#ef4444', 'DELETE'),
    'WatchEvent': ('#ff3e00', 'STAR'),
    'ForkEvent': ('#10b981', 'FORK'),
    'CommitCommentEvent': ('#60a5fa', 'COMMENT'),
    'default': ('#a3a3a3', 'INFO')
}

def get_github_activity():
    """Получает последнюю активность пользователя через GitHub API"""
    try:
        g = Github(GITHUB_TOKEN)
        user = g.get_user(GITHUB_USERNAME)
        events = list(user.get_events()[:MAX_EVENTS])
        
        activities = []
        for event in events:
            event_type = event.type
            color, status = EVENT_COLORS.get(event_type, EVENT_COLORS['default'])
            
            # Формируем описание события
            description = format_event_description(event)
            
            # Форматируем время
            timestamp = event.created_at.strftime('[%Y-%m-%d %H:%M:%S]')
            
            activities.append({
                'timestamp': timestamp,
                'status': status,
                'color': color,
                'description': description,
                'repo': event.repo.name if event.repo else ''
            })
        
        return activities
    
    except Exception as e:
        print(f"Error fetching GitHub activity: {e}")
        return get_fallback_activities()

def format_event_description(event):
    """Форматирует описание события"""
    event_type = event.type
    repo_name = event.repo.name.split('/')[-1] if event.repo else 'repository'
    
    descriptions = {
        'PushEvent': f"Pushed to {repo_name}",
        'PullRequestEvent': f"Pull request in {repo_name}",
        'IssuesEvent': f"Issue in {repo_name}",
        'CreateEvent': f"Created {event.payload.get('ref_type', 'branch')} in {repo_name}",
        'DeleteEvent': f"Deleted {event.payload.get('ref_type', 'branch')} in {repo_name}",
        'WatchEvent': f"Starred {repo_name}",
        'ForkEvent': f"Forked {repo_name}",
        'CommitCommentEvent': f"Commented on commit in {repo_name}"
    }
    
    return descriptions.get(event_type, f"Activity in {repo_name}")

def get_fallback_activities():
    """Возвращает демо-данные если API недоступен"""
    return [
        {
            'timestamp': '[2025-12-31 15:42:33]',
            'status': 'SUCCESS',
            'color': '#10b981',
            'description': 'Pushed to portfolio repository',
            'repo': 'portfolio'
        },
        {
            'timestamp': '[2025-12-31 14:18:45]',
            'status': 'COMMIT',
            'color': '#60a5fa',
            'description': 'Update README.md',
            'repo': 'keelbismark'
        },
        {
            'timestamp': '[2025-12-31 12:30:22]',
            'status': 'MERGE',
            'color': '#10b981',
            'description': 'Merged feature branch',
            'repo': 'project'
        }
    ]

def generate_svg(activities):
    """Генерирует SVG с анимацией на основе реальных данных"""
    
    svg_template = f'''<svg width="700" height="250" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      @keyframes blink {{
        0%, 49% {{ opacity: 1; }}
        50%, 100% {{ opacity: 0; }}
      }}
      @keyframes spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
      }}
'''
    
    # Генерируем анимации для каждой строки
    for i in range(len(activities)):
        delay = 10 + (i * 10)
        svg_template += f'''
      @keyframes fadeIn{i+1} {{
        0%, {delay}% {{ opacity: 0; }}
        {delay+5}% {{ opacity: 1; }}
        100% {{ opacity: 1; }}
      }}'''
    
    svg_template += '''
      
      .bg { fill: #050505; }
      .border { fill: none; stroke: #1f1f1f; stroke-width: 1; }
      .header-bg { fill: #0a0a0a; }
      
      .text-timestamp { fill: #525252; font-family: monospace; font-size: 10px; }
      .text-info { fill: #60a5fa; font-family: monospace; font-size: 11px; }
      .text-success { fill: #10b981; font-family: monospace; font-size: 11px; }
      .text-warning { fill: #fbbf24; font-family: monospace; font-size: 11px; }
      .text-error { fill: #ef4444; font-family: monospace; font-size: 11px; }
      .text-highlight { fill: #ff3e00; font-family: monospace; font-size: 11px; }
      .text-muted { fill: #a3a3a3; font-family: monospace; font-size: 11px; }
      .text-header { fill: #525252; font-family: monospace; font-size: 10px; }
      
      .cursor { fill: #ff3e00; animation: blink 0.8s step-end infinite; }
      .spinner { stroke: #ff3e00; stroke-width: 2; fill: none; animation: spin 1s linear infinite; }
    </style>
  </defs>
  
  <!-- Background -->
  <rect class="bg" width="700" height="250" rx="6"/>
  <rect class="border" x="0.5" y="0.5" width="699" height="249" rx="6"/>
  
  <!-- Header -->
  <rect class="header-bg" width="700" height="25" rx="6 6 0 0"/>
  <circle fill="#ff5f56" cx="15" cy="12.5" r="5"/>
  <circle fill="#ffbd2e" cx="35" cy="12.5" r="5"/>
  <circle fill="#27c93f" cx="55" cy="12.5" r="5"/>
  <text class="text-header" x="350" y="16" text-anchor="middle">tail -f /var/log/activity.log</text>
  
  <!-- Current time -->
  <text class="text-header" x="680" y="16" text-anchor="end">''' + datetime.now().strftime('%H:%M:%S') + '''</text>
  
  <!-- Content area -->
  <g transform="translate(15, 45)">
'''
    
    # Добавляем события
    y_offset = 0
    for i, activity in enumerate(activities):
        # Определяем класс цвета
        color_class = 'text-success' if 'SUCCESS' in activity['status'] else 'text-info'
        
        svg_template += f'''
    <g style="animation: fadeIn{i+1} 12s infinite; opacity: 0;" transform="translate(0, {y_offset})">
      <text class="text-timestamp" x="0" y="0">{activity['timestamp']}</text>
      <text class="{color_class}" x="150" y="0">[{activity['status']}]</text>
      <text class="text-muted" x="230" y="0">{activity['description']}</text>'''
        
        if activity['repo']:
            svg_template += f'''
      <text class="text-highlight" x="450" y="0">{activity['repo']}</text>'''
        
        svg_template += '''
    </g>
'''
        y_offset += 25
    
    # Добавляем футер
    svg_template += '''
  </g>
  
  <!-- Status bar at bottom -->
  <rect fill="#0a0a0a" x="0" y="225" width="700" height="25"/>
  <line stroke="#1f1f1f" x1="0" y1="225" x2="700" y2="225"/>
  
  <text class="text-info" x="15" y="241" font-size="10">
    <tspan fill="#10b981">●</tspan> Live activity feed from GitHub
  </text>
  
  <text class="text-muted" x="685" y="241" text-anchor="end" font-size="10">
    Updated: ''' + datetime.now().strftime('%Y-%m-%d %H:%M UTC') + '''
  </text>
</svg>'''
    
    return svg_template

def main():
    """Основная функция"""
    print("🔄 Fetching GitHub activity...")
    activities = get_github_activity()
    
    print(f"✅ Found {len(activities)} recent activities")
    
    print("🎨 Generating SVG...")
    svg_content = generate_svg(activities)
    
    # Создаем директорию если не существует
    os.makedirs('assets', exist_ok=True)
    
    # Сохраняем SVG
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    
    print(f"✅ Activity log saved to {OUTPUT_FILE}")
    
    # Выводим список событий
    print("\n📋 Recent activity:")
    for activity in activities:
        print(f"  {activity['timestamp']} [{activity['status']}] {activity['description']}")

if __name__ == '__main__':
    main()