import os
import re
from pathlib import Path
from typing import Dict, List, Optional

def normalize_genre(genre: str) -> str:
    """
    Normalize genre names by lowercasing and standardizing variations.
    """
    genre = genre.lower().strip()
    
    # Remove wiki markup [[Genre]] or [[Genre|Display]]
    genre = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', genre)
    
    # Remove any remaining brackets
    genre = re.sub(r'[\[\]]', '', genre)
    
    # Remove references like <ref>...</ref> or <ref name="..."/>
    genre = re.sub(r'<ref[^>]*>.*?</ref>', '', genre, flags=re.DOTALL)
    genre = re.sub(r'<ref[^>]*/>', '', genre)
    genre = re.sub(r'<ref[^>]*>', '', genre)
    
    # Remove HTML comments
    genre = re.sub(r'<!--.*?-->', '', genre, flags=re.DOTALL)
    
    # Remove URLs
    genre = re.sub(r'https?://[^\s]+', '', genre)
    genre = re.sub(r'www\.[^\s]+', '', genre)
    
    # Remove curly braces and quotes
    genre = re.sub(r'[{}"\'`]', '', genre)
    
    # Standardize rock and roll variations
    rock_variations = {
        "rock 'n' roll": "rock and roll",
        "rock n roll": "rock and roll",
        "rock'n'roll": "rock and roll",
        "rock & roll": "rock and roll",
        "rock n' roll": "rock and roll"
    }
    
    for variant, standard in rock_variations.items():
        if genre == variant:
            genre = standard
    
    # Clean up whitespace
    genre = ' '.join(genre.split())
    
    return genre.strip()

def extract_nested_content(text: str, open_char: str = '{', close_char: str = '}') -> str:
    """
    Extract content with properly matched nested brackets.
    """
    if open_char not in text:
        return text
        
    result = []
    depth = 0
    start_idx = text.find(open_char)
    
    if start_idx == -1:
        return text
        
    for i, char in enumerate(text[start_idx:], start_idx):
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                result.append(text[start_idx:i+1])
                break
        
    return ''.join(result) if result else text

def parse_genre_field(genre_text: str) -> List[str]:
    """
    Parse various wiki formats for genres.
    """
    genres = []
    
    # Remove HTML comments first
    genre_text = re.sub(r'<!--.*?-->', '', genre_text, flags=re.DOTALL)

    # FIRST: Remove all reference tags and their content before processing
    # This is the key fix - do this BEFORE any other processing
    genre_text = re.sub(r'<ref[^>]*>.*?</ref>', '', genre_text, flags=re.DOTALL)
    genre_text = re.sub(r'<ref[^>]*/>', '', genre_text)

    # Remove template name and brackets
    genre_text = re.sub(r'^\{\{[^|]*\|?', '', genre_text)
    genre_text = re.sub(r'\}\}$', '', genre_text)

    # Handle {{nowrap|...}} templates
    genre_text = re.sub(r'\{\{nowrap\|([^}]+)\}\}', r'\1', genre_text, flags=re.IGNORECASE)
    
    # Handle {{flatlist|...}} or {{hlist|...}} templates
    if re.search(r'\{\{(flatlist|hlist|flat list|unbulleted list|plainlist)', genre_text, re.IGNORECASE):
        # Extract the template content
        template_match = re.search(r'\{\{(?:flatlist|hlist|flat list|unbulleted list|plainlist)[^{]*', genre_text, re.IGNORECASE)
        if template_match:
            # Find the complete template including nested templates
            template_start = template_match.start()
            template_text = genre_text[template_start:]
            
            # Count brackets to find the end
            depth = 0
            end_pos = 0
            for i, char in enumerate(template_text):
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 1
                        break
            
            if end_pos > 0:
                template_content = template_text[:end_pos]
                
                # Remove template wrapper
                template_content = re.sub(r'^\{\{[^|]*\|?', '', template_content)
                template_content = re.sub(r'\}\}$', '', template_content)
                
                # Parse items (handle both * lists and | separated)
                if '*' in template_content:
                    items = re.split(r'\*+', template_content)
                else:
                    items = re.split(r'\|', template_content)
                
                for item in items:
                    item = item.strip()
                    if item:
                        # Handle wiki links
                        item = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', item)
                        # Remove nowrap
                        item = re.sub(r'\{\{nowrap\|([^}]+)\}\}', r'\1', item, flags=re.IGNORECASE)
                        # Remove parenthetical additions
                        if '(' in item:
                            # Keep content in parentheses if it contains "early", "later", etc.
                            if re.search(r'\(.*(?:early|later|late|mid).*\)', item, re.IGNORECASE):
                                # Keep it as is or you could append it
                                pass
                            else:
                                item = re.sub(r'\([^)]*\)', '', item)
                        
                        item = item.strip()
                        if item and not item.startswith('<!--'):
                            genres.append(item)
    else:
        # Handle simple formats
        # Remove <br> tags
        genre_text = re.sub(r'<br\s*/?>', ',', genre_text, flags=re.IGNORECASE)
        
        # Split by common delimiters
        raw_genres = re.split(r'[,;/\n•·|]', genre_text)
        
        for genre in raw_genres:
            genre = genre.strip()
            
            # Handle wiki links
            if '[[' in genre:
                genre = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', genre)
            
            # Skip if empty or template/comment
            if not genre or genre.startswith('{{') or genre.startswith('<!--') or genre.startswith('<ref'):
                continue
            
            genres.append(genre)
    
    # Normalize all genres
    normalized_genres = []
    for genre in genres:


        genre = genre.replace('*', '').strip()
    
        normalized = normalize_genre(genre)


        
        # Filter out common non-genre terms and artifacts
        skip_terms = ['music', 'band', 'group', '', 'cite web', 'cite book', 
             'first', 'last', 'url', 'title', 'ref', 'name', 'am',
             'allmusic', 'www', 'com', 'http', 'https', 'ref name',
             'work', 'date', 'publisher', 'website', 'access-date',
             'archive-date', 'archive-url', 'page', 'isbn', 'year',
             'citation', 'url-status', 'live', 'rock music', 'rock']
        
        # Check if it's actually a genre (not just punctuation or a skip term)
        if normalized and len(normalized) > 1 and normalized not in skip_terms:
            # Additional check: if it contains 'ref' or 'cite' it's probably not a genre
            if 'ref' not in normalized and 'cite' not in normalized and '.' not in normalized:
                if normalized not in normalized_genres:
                    normalized_genres.append(normalized)
    
    return normalized_genres

def extract_genres_from_infobox(text: str) -> Optional[List[str]]:
    """
    Extract genres from the infobox section of a Wikipedia page text.
    Returns None if no infobox or no genre field found.
    """
    # Find infobox with better pattern
    infobox_pattern = r'\{\{Infobox[^{]*'
    infobox_match = re.search(infobox_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if not infobox_match:
        return None
    
    # Find the complete infobox by counting brackets
    infobox_start = infobox_match.start()
    text_from_start = text[infobox_start:]
    
    depth = 0
    infobox_end = len(text_from_start)
    
    for i, char in enumerate(text_from_start):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                infobox_end = i + 1
                break
    
    infobox_text = text_from_start[:infobox_end]
    
    # Look for genre or genres field - match everything until we hit another field (|) at the same depth
    # This pattern looks for | genre = and captures everything until the next | at the base level
    lines = infobox_text.split('\n')
    
    genre_content = []
    in_genre_field = False
    bracket_depth = 0
    
    for line in lines:
        # Check if this line starts a genre field
        if re.match(r'\s*\|\s*genres?\s*=', line, re.IGNORECASE):
            in_genre_field = True
            # Get the content after the = sign
            genre_line = re.sub(r'^\s*\|\s*genres?\s*=\s*', '', line, flags=re.IGNORECASE)
            genre_content.append(genre_line)
            # Count brackets in this line
            bracket_depth = genre_line.count('{') - genre_line.count('}')
        elif in_genre_field:
            # Check if we've hit a new field (line starting with | and bracket depth is 0)
            if line.strip().startswith('|') and bracket_depth == 0:
                in_genre_field = False
                break
            else:
                genre_content.append(line)
                bracket_depth += line.count('{') - line.count('}')
    
    if not genre_content:
        return None
    
    genre_text = '\n'.join(genre_content)
    
    # Parse the genre field
    genres = parse_genre_field(genre_text)
    
    return genres if genres else None

def extract_artist_name_from_filename(filename: str) -> str:
    """
    Extract artist name from filename.
    """
    # Remove .txt extension
    name = os.path.splitext(filename)[0]
    
    # Replace underscores with spaces if present
    name = name.replace('_', ' ')
    
    # Remove "(band)" or similar suffixes if present
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
    
    return name.strip()

def process_wiki_files(folder_path: str) -> Dict[str, List[str]]:
    """
    Process all .txt files in the folder and extract genres for each artist.
    """
    artist_genres = {}
    
    # Convert to Path object
    folder = Path(folder_path)
    
    if not folder.exists():
        raise ValueError(f"Folder {folder_path} does not exist")
    
    # Process all .txt files
    txt_files = list(folder.glob("*.txt"))
    
    print(f"Found {len(txt_files)} .txt files to process...")
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for file_path in txt_files:
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Extract artist name from filename
            artist_name = extract_artist_name_from_filename(file_path.name)
            
            # Extract genres from infobox
            genres = extract_genres_from_infobox(content)
            
            if genres:
                artist_genres[artist_name] = genres
                print(f"✓ {artist_name}: {', '.join(genres)}")
                success_count += 1
            else:
                print(f"✗ {artist_name}: No genres found in infobox")
                failure_count += 1
                
        except Exception as e:
            print(f"ERROR processing {file_path.name}: {e}")
            failure_count += 1
    
    print("-" * 50)
    print(f"\nProcessing complete!")
    print(f"  Success: {success_count} artists with genres extracted")
    print(f"  Failed: {failure_count} artists without genres")
    
    return artist_genres

# Main execution
if __name__ == "__main__":
    # Set your folder path here
    FOLDER_PATH = "assignments/Assignment 1/wiki_pages"  # Change this to your actual folder path
    
    try:
        # Extract genres
        artist_genre_dict = process_wiki_files(FOLDER_PATH)
        
        # Print summary statistics
        print("\n" + "="*50)
        print("SUMMARY STATISTICS")
        print("="*50)
        
        # Count total unique genres
        all_genres = set()
        for genres in artist_genre_dict.values():
            all_genres.update(genres)
        
        print(f"Total artists with genres: {len(artist_genre_dict)}")
        print(f"Total unique genres found: {len(all_genres)}")
        
        # Show most common genres
        from collections import Counter
        genre_counter = Counter()
        for genres in artist_genre_dict.values():
            genre_counter.update(genres)
        
        print("\nTop 15 most common genres:")
        for genre, count in genre_counter.most_common(15):
            print(f"  {genre}: {count} artists")
        
        # Optionally save to JSON file
        import json
        output_file = "artist_genres_without_rock.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(artist_genre_dict, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")

        