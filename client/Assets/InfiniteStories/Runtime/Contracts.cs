using System;

namespace InfiniteStories
{
    // Versioned wire DTOs. Only server-confirmed snapshots are authoritative.
    [Serializable] public class Interest { public string name; public string category; public string entity_id; }
    [Serializable] public class NewGameRequest { public string request_id; public string mode; public Interest[] interests; }
    [Serializable] public class GenerationRecoveryRequest { public NewGameRequest creation; public string previous_session_id; }
    [Serializable] public class Command { public string kind; public string target = ""; public string choice = ""; public float x; public float y; }
    [Serializable] public class ActionRequest { public string request_id; public int expected_revision; public Command command; }
    [Serializable] public class TurnRequest { public string request_id; public int expected_revision; public string text; }
    [Serializable] public class GameState
    {
        public int schema_version; public string chapter_id; public int chapter_version; public string mode;
        public string location_id; public float x; public float y; public int visits;
        public string[] flags; public string[] choices; public string ending; public string[] history; public string cultural_source;
        public Interest[] interests; public CulturalContext cultural_context;
    }
    [Serializable] public class StoryChoice { public string id; public string label; public string text; public string[] requires; public string[] grants; public string ending; }
    [Serializable] public class WorldObject
    {
        public string id; public string name; public string kind; public float x; public float y; public string text;
        public string destination; public StoryChoice[] choices;
    }
    [Serializable] public class Location
    {
        public string id; public string name; public string description; public int width; public int height;
        public string[] rows; public WorldObject[] objects;
        public void Validate()
        {
            if (width < 8 || width > 64 || height < 8 || height > 64 || rows == null || rows.Length != height || objects == null)
                throw new ArgumentException("The area data is invalid.");
            foreach (string row in rows)
            {
                if (row == null || row.Length != width) throw new ArgumentException("The tile data is invalid.");
                foreach (char tile in row) if (tile != '0' && tile != '1' && tile != '2') throw new ArgumentException("Unknown tile.");
            }
        }
    }
    [Serializable] public class Objective { public string id; public string label; public bool completed; }
    [Serializable] public class GameView
    {
        public int schema_version; public string session_id; public int revision; public GameState state;
        public Location location; public WorldObject[] nearby; public Objective[] objectives;
        public string narrative; public string narrative_source; public string[] notices; public bool idempotent_replay;
    }
    [Serializable] public class CulturalTag { public string id, name, type; }
    [Serializable] public class CulturalEvidence { public string origin, path, retrieved_at, body_sha256; public int elapsed_ms; }
    [Serializable] public class CulturalEntity { public string entity_id, name, category, description, content_rating, disambiguation; public int year; public CulturalTag[] tags; }
    [Serializable] public class CulturalLink { public CulturalEntity seed; public CulturalEntity[] recommendations; public string selected_id, setting; public CulturalEvidence[] evidence; }
    [Serializable] public class CulturalContext { public int schema_version; public string source,rule_version; public CulturalLink[] links; }
    [Serializable] public class EntityCandidate { public string entity_id, name, category, disambiguation; }
    [Serializable] public class ErrorDetails { public int interest_index; public EntityCandidate[] candidates; }
    [Serializable] public class Capabilities { public int schema_version; public bool cultural_generation; public string[] cultural_categories; public string verification_mode; public string game_master_inference_mode; }
    [Serializable] public class ApiError { public string code; public string message; public string request_id; public ErrorDetails details; }
    [Serializable] public class ErrorEnvelope { public ApiError error; }
    [Serializable] public class PendingRequest { public string path; public string method; public string json; }
}
