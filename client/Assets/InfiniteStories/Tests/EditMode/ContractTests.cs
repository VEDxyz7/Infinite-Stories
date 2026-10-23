using System;
using NUnit.Framework;
using UnityEngine;

namespace InfiniteStories.Tests
{
    public sealed class ContractTests
    {
        [Test] public void InvalidTileContentCannotLoad()
        {
            var area=new Location { width=8,height=8,rows=new[] { "bad" },objects=Array.Empty<WorldObject>() };
            Assert.Throws<ArgumentException>(() => area.Validate());
        }
        [TestCase("http://remote.example")]
        [TestCase("https://example.com/?api_key=secret")]
        [TestCase("https://user:secret@example.com")]
        public void ReleaseConfigurationRejectsUnsafeOrigins(string value)
        {
            var settings=ScriptableObject.CreateInstance<ClientSettings>(); settings.apiOrigin=value;
            Assert.Throws<ArgumentException>(() => settings.Validate(true)); UnityEngine.Object.DestroyImmediate(settings);
        }
        [Test] public void CulturalInputsExcludeBooksAndKeepVerifiedDirections()
        {
            CollectionAssert.AreEquivalent(new[] {"artist","movie","brand","videogame"},GameUI.SupportedCategories);
            CollectionAssert.DoesNotContain(GameUI.SupportedCategories,"book");
            var choice=JsonUtility.FromJson<ErrorEnvelope>("{\"error\":{\"code\":\"QLOO_AMBIGUOUS\",\"details\":{\"interest_index\":0,\"candidates\":[{\"entity_id\":\"actual-response-id\",\"name\":\"The Lego Group\",\"category\":\"brand\"}]}}}");
            Assert.AreEqual("The Lego Group",choice.error.details.candidates[0].name);
        }
        [Test] public void CulturalStateWireContractRetainsAttribution()
        {
            var state=JsonUtility.FromJson<GameState>("{\"schema_version\":1,\"mode\":\"cultural\",\"cultural_source\":\"qloo\",\"cultural_context\":{\"schema_version\":1,\"source\":\"qloo\",\"links\":[{\"seed\":{\"name\":\"David Bowie\"},\"selected_id\":\"selected\",\"setting\":\"Paper theater\"}]}}");
            Assert.AreEqual("qloo",state.cultural_source);
            Assert.AreEqual("David Bowie",state.cultural_context.links[0].seed.name);
        }
        [Test] public void ConversationRulesAndValidationSurviveWireRoundtrip()
        {
            var state=new GameState{visit_rules="conversation-v1",visits=12,encounter_id="beacon",activation_validation=new ActivationValidation{version="engine-witness-v1",candidate=1,steps=200,visits=4,ending="together"}};
            var copy=JsonUtility.FromJson<GameState>(JsonUtility.ToJson(state));
            Assert.AreEqual("conversation-v1",copy.visit_rules);Assert.AreEqual(12,copy.visits);Assert.AreEqual("beacon",copy.encounter_id);
            Assert.AreEqual("engine-witness-v1",copy.activation_validation.version);Assert.AreEqual(1,copy.activation_validation.candidate);
            var legacy=JsonUtility.FromJson<GameState>("{\"visits\":4}");Assert.AreEqual(4,legacy.visits);Assert.IsTrue(legacy.activation_validation==null || string.IsNullOrEmpty(legacy.activation_validation.version));
        }
        [Test] public void AgentToolObservationKeepsConfirmedProvenance()
        {
            var view=JsonUtility.FromJson<GameView>("{\"narrative_source\":\"confirmed_state_tool\",\"tool_results\":[{\"tool_id\":\"check_progress\",\"arguments\":{\"scope\":\"commitments\"},\"result\":{\"visits_spent\":3,\"commitments\":[{\"choice_id\":\"take_map\",\"confirmed_grants\":[\"map\"]}]}}]}");
            Assert.AreEqual("confirmed_state_tool",view.narrative_source);
            Assert.AreEqual("check_progress",view.tool_results[0].tool_id);
            Assert.AreEqual(3,view.tool_results[0].result.visits_spent);
            Assert.AreEqual("take_map",view.tool_results[0].result.commitments[0].choice_id);
        }
        [Test] public void UnderstandingRecordsAreReadOnlyAndSurviveResumeContract()
        {
            var state=new GameState { cultural_context=new CulturalContext { rule_version="cultural-understanding-v3" }, understanding_records=new[] {
                new UnderstandingRecord { resident="mara", choice_id="take_map", evidence_sha256="saved-evidence", explanation="A broad association, not my identity.",
                    assessment=new UnderstandingAssessment { status="supported", source_id="saved-seed", target_id="saved-target",commitment_quote="I will keep the letters private." },
                    review=new UnderstandingReview { connection_meaning="association_explanation", limitation_meaning="acknowledges_evidence_limits" } }
            }};
            var copy=JsonUtility.FromJson<GameState>(JsonUtility.ToJson(state));
            Assert.AreEqual("cultural-understanding-v3",copy.cultural_context.rule_version);
            Assert.AreEqual("mara",copy.understanding_records[0].resident);
            Assert.AreEqual("I will keep the letters private.",copy.understanding_records[0].assessment.commitment_quote);
            Assert.AreEqual("acknowledges_evidence_limits",copy.understanding_records[0].review.limitation_meaning);
            Assert.IsFalse(JsonUtility.ToJson(new Command { kind="choose",target="mara",choice="take_map" }).Contains("assessment"));
        }
        [Test] public void ProceduralCityIsReadOnlyAndUnknownContrastRemainsUnknown()
        {
            var state=JsonUtility.FromJson<GameState>("{\"city_generation\":{\"version\":\"saved-cultural-city-v1\",\"seed\":\"saved-seed\",\"template\":2,\"proof_order\":[1,0],\"resident_links\":{\"mara\":1,\"ivo\":0,\"sera\":1},\"distances\":[{\"contrast\":null,\"metadata_status\":\"unknown\"},{\"contrast\":0.75,\"metadata_status\":\"comparable\"}]}}");
            Assert.AreEqual(2,state.city_generation.template);
            Assert.AreEqual(1,state.city_generation.resident_links.mara);
            Assert.IsNull(state.city_generation.distances[0].ComparableContrast);
            Assert.AreEqual(0.75f,state.city_generation.distances[1].ComparableContrast.Value);
            Assert.IsFalse(JsonUtility.ToJson(new Command { kind="choose" }).Contains("city_generation"));
        }
        [Test] public void ActionWireContractKeepsIdAndRevision()
        {
            var command=new ActionRequest { request_id="test-only", expected_revision=7,command=new Command { kind="choose",target="mara",choice="take_map" } };
            var copy=JsonUtility.FromJson<ActionRequest>(JsonUtility.ToJson(command));
            Assert.AreEqual(7,copy.expected_revision); Assert.AreEqual("take_map",copy.command.choice);
        }
    }
}
