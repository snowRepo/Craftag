use lofty::file::{AudioFile as LoftyAudioFile, TaggedFileExt};
use lofty::tag::{Accessor, ItemKey, Tag};
use lofty::picture::{Picture, PictureType, MimeType};
use lofty::probe::Probe;
use lofty::config::WriteOptions;
use serde::{Deserialize, Serialize};
use std::path::Path;
use walkdir::WalkDir;
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64_STANDARD};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AudioFile {
    pub path: String,
    pub filename: String,
    pub title: Option<String>,
    pub artist: Option<String>,
    pub album: Option<String>,
    pub year: Option<u32>,
    pub genre: Option<String>,
    pub track: Option<u32>,
    pub album_artist: Option<String>,
    pub composer: Option<String>,
    pub disc: Option<u32>,
    pub comments: Option<String>,
    pub has_art: bool,
}

fn parse_file(path: &Path) -> Result<AudioFile, String> {
    let tagged_file = Probe::open(path)
        .map_err(|e| e.to_string())?
        .read()
        .map_err(|e| e.to_string())?;

    let tag = match tagged_file.primary_tag() {
        Some(primary_tag) => Some(primary_tag),
        None => tagged_file.first_tag(),
    };

    let filename = path.file_name().unwrap_or_default().to_string_lossy().to_string();
    let path_str = path.to_string_lossy().to_string();

    if let Some(t) = tag {
        Ok(AudioFile {
            path: path_str,
            filename,
            title: t.title().map(|s| s.into_owned()),
            artist: t.artist().map(|s| s.into_owned()),
            album: t.album().map(|s| s.into_owned()),
            year: t.get(ItemKey::Year).and_then(|i| i.value().text()).and_then(|t| t.parse::<u32>().ok()),
            genre: t.genre().map(|s| s.into_owned()),
            track: t.track(),
            album_artist: t.get(ItemKey::AlbumArtist).and_then(|i| i.value().text()).map(|s| s.to_string()),
            composer: t.get(ItemKey::Composer).and_then(|i| i.value().text()).map(|s| s.to_string()),
            disc: t.disk(),
            comments: t.get(ItemKey::Comment).and_then(|i| i.value().text()).map(|s| s.to_string()),
            has_art: !t.pictures().is_empty(),
        })
    } else {
        Ok(AudioFile {
            path: path_str,
            filename,
            title: None,
            artist: None,
            album: None,
            year: None,
            genre: None,
            track: None,
            album_artist: None,
            composer: None,
            disc: None,
            comments: None,
            has_art: false,
        })
    }
}

#[tauri::command]
fn read_audio_tags(paths: Vec<String>) -> Result<Vec<AudioFile>, String> {
    let mut results = Vec::new();

    for path_str in paths {
        let path = Path::new(&path_str);
        if path.is_dir() {
            for entry in WalkDir::new(path).into_iter().filter_map(|e| e.ok()) {
                let p = entry.path();
                if p.is_file() {
                    if let Ok(audio_file) = parse_file(p) {
                        results.push(audio_file);
                    }
                }
            }
        } else if path.is_file() {
            if let Ok(audio_file) = parse_file(path) {
                results.push(audio_file);
            }
        }
    }

    Ok(results)
}

#[tauri::command]
fn get_album_art(path: String) -> Result<Option<String>, String> {
    let tagged_file = Probe::open(&path)
        .map_err(|e| e.to_string())?
        .read()
        .map_err(|e| e.to_string())?;

    let tag = match tagged_file.primary_tag() {
        Some(primary_tag) => Some(primary_tag),
        None => tagged_file.first_tag(),
    };

    if let Some(t) = tag {
        if let Some(pic) = t.pictures().first() {
            let data = pic.data();
            let mime = pic.mime_type().map(|m| m.as_str()).unwrap_or("image/jpeg");
            let b64 = BASE64_STANDARD.encode(data);
            return Ok(Some(format!("data:{};base64,{}", mime, b64)));
        }
    }
    Ok(None)
}

#[tauri::command]
fn save_audio_tags(file: AudioFile) -> Result<(), String> {
    let mut tagged_file = Probe::open(&file.path)
        .map_err(|e| e.to_string())?
        .read()
        .map_err(|e| e.to_string())?;

    let tag_type = tagged_file.primary_tag_type();

    // Ensure there is a tag we can write to.
    if tagged_file.primary_tag().is_none() {
        tagged_file.insert_tag(Tag::new(tag_type));
    }

    if let Some(tag) = tagged_file.primary_tag_mut() {
        if let Some(title) = file.title { tag.set_title(title); } else { tag.remove_title(); }
        if let Some(artist) = file.artist { tag.set_artist(artist); } else { tag.remove_artist(); }
        if let Some(album) = file.album { tag.set_album(album); } else { tag.remove_album(); }
        if let Some(year) = file.year {
            tag.insert_text(ItemKey::Year, year.to_string());
        } else {
            tag.remove_key(ItemKey::Year);
        }
        if let Some(genre) = file.genre { tag.set_genre(genre); } else { tag.remove_genre(); }
        if let Some(track) = file.track { tag.set_track(track); } else { tag.remove_track(); }
        if let Some(album_artist) = file.album_artist { tag.insert_text(ItemKey::AlbumArtist, album_artist); } else { tag.remove_key(ItemKey::AlbumArtist); }
        if let Some(composer) = file.composer { tag.insert_text(ItemKey::Composer, composer); } else { tag.remove_key(ItemKey::Composer); }
        if let Some(disc) = file.disc { tag.set_disk(disc); } else { tag.remove_disk(); }
        if let Some(comments) = file.comments { tag.insert_text(ItemKey::Comment, comments); } else { tag.remove_key(ItemKey::Comment); }
    }

    tagged_file
        .save_to_path(&file.path, WriteOptions::default())
        .map_err(|e| e.to_string())?;

    Ok(())
}

/// Embeds an image file into an audio file's tag as front cover art.
/// Works cross-platform — `image_path` is an absolute path to any JPEG/PNG.
#[tauri::command]
fn set_album_art(audio_path: String, image_path: String) -> Result<(), String> {
    let img_bytes = std::fs::read(&image_path).map_err(|e| e.to_string())?;

    // Detect MIME type from extension
    let ext = Path::new(&image_path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    let mime = match ext.as_str() {
        "jpg" | "jpeg" => MimeType::Jpeg,
        "png"          => MimeType::Png,
        "gif"          => MimeType::Gif,
        "bmp"          => MimeType::Bmp,
        _              => MimeType::Jpeg, // sensible fallback
    };

    let picture = Picture::unchecked(img_bytes)
        .pic_type(PictureType::CoverFront)
        .mime_type(mime)
        .build();

    let mut tagged_file = Probe::open(&audio_path)
        .map_err(|e| e.to_string())?
        .read()
        .map_err(|e| e.to_string())?;

    let tag_type = tagged_file.primary_tag_type();
    if tagged_file.primary_tag().is_none() {
        tagged_file.insert_tag(Tag::new(tag_type));
    }

    if let Some(tag) = tagged_file.primary_tag_mut() {
        // Remove existing cover art before inserting the new one
        tag.remove_picture_type(PictureType::CoverFront);
        tag.push_picture(picture);
    }

    tagged_file
        .save_to_path(&audio_path, WriteOptions::default())
        .map_err(|e| e.to_string())?;

    Ok(())
}

/// Strips all embedded pictures from an audio file's tag.
#[tauri::command]
fn remove_album_art(audio_path: String) -> Result<(), String> {
    let mut tagged_file = Probe::open(&audio_path)
        .map_err(|e| e.to_string())?
        .read()
        .map_err(|e| e.to_string())?;

    if let Some(tag) = tagged_file.primary_tag_mut() {
        // Remove all known picture types
        for pic_type in [
            PictureType::CoverFront,
            PictureType::CoverBack,
            PictureType::Other,
            PictureType::OtherIcon,
        ] {
            tag.remove_picture_type(pic_type);
        }
    }

    tagged_file
        .save_to_path(&audio_path, WriteOptions::default())
        .map_err(|e| e.to_string())?;

    Ok(())
}

/// Reads an image file and returns it as a base64 data URL for preview.
#[tauri::command]
fn read_image(path: String) -> Result<String, String> {
    let bytes = std::fs::read(&path).map_err(|e| e.to_string())?;
    let ext = Path::new(&path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();
    let mime = match ext.as_str() {
        "png"  => "image/png",
        "gif"  => "image/gif",
        "bmp"  => "image/bmp",
        "webp" => "image/webp",
        _      => "image/jpeg",
    };
    Ok(format!("data:{};base64,{}", mime, BASE64_STANDARD.encode(&bytes)))
}


pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .invoke_handler(tauri::generate_handler![
            read_audio_tags,
            get_album_art,
            save_audio_tags,
            set_album_art,
            remove_album_art,
            read_image,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application")
}
