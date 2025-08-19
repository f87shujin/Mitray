# 🎵 Multi-Source Music System Setup

## Overview
The bot now supports multiple music sources instead of just YouTube, making it more reliable and feature-rich.

## 🎧 Available Music Sources

### 1. **Spotify** (Primary)
- **Status**: ✅ Enabled by default
- **Features**: Search and find tracks
- **Limitation**: Cannot play directly (no direct audio URLs)
- **Use Case**: Track discovery and information

### 2. **SoundCloud** (Primary)
- **Status**: ✅ Enabled by default  
- **Features**: Search and play tracks directly
- **Requirement**: Client ID for streaming

### 3. **YouTube** (Fallback)
- **Status**: ❌ Disabled by default, but available as fallback
- **Features**: Full playback support
- **Use Case**: When other sources fail

## 🔑 Required Credentials

Add these to your `.env` file:

```env
# Spotify API
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here

# SoundCloud API  
SOUNDCLOUD_CLIENT_ID=your_soundcloud_client_id_here
```

## 📋 How to Get Credentials

### Spotify API
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Copy `Client ID` and `Client Secret`

### SoundCloud API
1. Go to [SoundCloud for Developers](https://developers.soundcloud.com/)
2. Create a new app
3. Copy `Client ID`

## 🎮 Commands

- **`mit play song_name`** - Play music from available sources
- **`mit next song_name`** - Add song to queue
- **`mit stop`** - Stop music and leave channel
- **`mit sources`** - Show music sources status

## 🔄 How It Works

1. **Primary Search**: Tries Spotify first (for discovery)
2. **Playback Attempt**: Tries SoundCloud for direct playback
3. **Fallback**: Uses YouTube if other sources fail
4. **Smart Routing**: Automatically chooses best available source

## 🚀 Benefits

✅ **More Reliable** - Multiple sources = higher success rate  
✅ **Better Quality** - SoundCloud often has better audio  
✅ **No SSL Issues** - Avoids YouTube's certificate problems  
✅ **Faster Search** - API-based search is quicker  
✅ **Better Metadata** - Artist names, track info, etc.  

## 🧪 Testing

1. **Check Sources**: `mit sources`
2. **Test Play**: `mit play despacito`
3. **Test Queue**: `mit next shape of you`
4. **Stop**: `mit stop`

## 🔧 Troubleshooting

- **No Credentials**: Set up API keys in `.env`
- **Source Disabled**: Check `music_sources` configuration
- **Playback Fails**: Check FFmpeg installation
- **No Results**: Try different search terms
