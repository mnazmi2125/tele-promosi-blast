module.exports = {
  apps: [
    {
      name: 'panel',
      script: 'panel.py',
      interpreter: 'python3',
      cwd: '/root/telegram-bot',
      autorestart: true,
      restart_delay: 15000,
      max_restarts: 50,
      time: true
    }
  ]
};
