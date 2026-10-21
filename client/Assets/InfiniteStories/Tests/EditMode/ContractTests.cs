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
        [Test] public void ActionWireContractKeepsIdAndRevision()
        {
            var command=new ActionRequest { request_id="test-only", expected_revision=7,command=new Command { kind="choose",target="mara",choice="take_map" } };
            var copy=JsonUtility.FromJson<ActionRequest>(JsonUtility.ToJson(command));
            Assert.AreEqual(7,copy.expected_revision); Assert.AreEqual("take_map",copy.command.choice);
        }
    }
}
