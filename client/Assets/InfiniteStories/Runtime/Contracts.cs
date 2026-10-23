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
        public string visit_rules; public string encounter_id; public ActivationValidation activation_validation; public CityGeneration city_generation;
        public UnderstandingRecord[] understanding_records;
        public string[] flags; public string[] choices; public string ending; public string[] history; public string cultural_source;
        public Interest[] interests; public CulturalContext cultural_context;
        public GenericControl generic_control; public TasteCard taste_card;
    }
    [Serializable] public class GenericControl { public string version,seed,source,record,film,motif; }
    [Serializable] public class TasteRelationship { public CulturalEntity source,target; public CulturalEvidence[] provenance; public string explanation; }
    [Serializable] public class TasteCard
    {
        public string version,domain,ending,profile,profile_basis,recommendations_note;
        public Interest[] favourites; public string[] discoveries,metadata_labels;
        public CulturalEntity[] encountered; public TasteRelationship[] relationships,try_next;
    }
    [Serializable] public class ActivationValidation { public string version; public int candidate; public string evidence_sha256, chapter_sha256, commands_sha256, generation_sha256, generated_chapter_sha256; public int steps, visits; public string ending; }
    [Serializable] public class ResidentLinks { public int mara, ivo, sera; }
    [Serializable] public class CulturalDistance
    {
        public string source_id, target_id, metadata_status, relationship, method;
        public string[] comparable_domains, shared_tags;
        public float contrast;
        public float? ComparableContrast { get { return metadata_status=="comparable" ? (float?)contrast : null; } }
    }
    [Serializable] public class CityGeneration
    {
        public string version, seed; public int candidate, template;
        public int[] proof_order; public string[] trace_locations, card_locations, shortcut;
        public ResidentLinks resident_links; public CulturalDistance[] distances;
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
        public ToolObservation[] tool_results;
    }
    // Read-only server observations; these DTOs never grant client authority.
    [Serializable] public class ToolObservation { public string tool_id; public ToolArguments arguments; public ToolResult result; }
    [Serializable] public class ToolArguments { public string query,category,entity_id,source_id,target_id,claim,scope,action_id,requested_name,pair; }
    [Serializable] public class ConfirmedCommitment { public string choice_id,label; public string[] confirmed_grants; }
    [Serializable] public class ToolResult
    {
        public string status,scope,claim,limitations,original_story_interpretation,requested_scope,visit_rules,encounter_id,ending,history_limit,message;
        public CulturalEntity[] entities; public CulturalEntity source,target; public CulturalEvidence[] provenance;
        public Objective[] objectives; public string[] discoveries,unrecognized_choice_ids,proposed_grants;
        public ConfirmedCommitment[] commitments; public int visits_spent,visits_remaining; public Command command;
    }
    // Read-only server-confirmed assessments; never sent in a Command.
    [Serializable] public class UnderstandingAssessment
    {
        public bool attempt,addresses_affinity,respects_limits,separates_fiction,explicit_choice;
        public string choice_id,status,source_id,target_id,connection_quote,limitation_quote,interpretation_quote,commitment_quote;
        public int link_index;
    }
    [Serializable] public class UnderstandingReview { public string connection_meaning,limitation_meaning,fiction_meaning,choice_meaning; }
    [Serializable] public class UnderstandingRecord
    {
        public string resident,choice_id,evidence_sha256,explanation;
        public UnderstandingAssessment assessment; public UnderstandingReview review;
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
