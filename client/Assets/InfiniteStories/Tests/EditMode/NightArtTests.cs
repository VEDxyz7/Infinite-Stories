using System;
using NUnit.Framework;
using UnityEngine;

namespace InfiniteStories.Tests
{
    public sealed class NightArtTests
    {
        [Test] public void ImportedActorsHaveDistinctFourDirectionStandingAndWalkingFrames()
        {
            var sprites=new System.Collections.Generic.HashSet<Sprite>();
            foreach(int actor in new[]{0,1,2,3,5})for(int direction=0;direction<4;direction++)for(int frame=0;frame<3;frame++) {
                var sprite=NightArt.Character(actor,direction,frame);
                Assert.IsNotNull(sprite,$"Missing actor{actor}, direction{direction}, frame{frame}");
                Assert.IsTrue(sprites.Add(sprite),"Each imported animation pose must be a distinct source file.");
                Assert.AreEqual(new Vector2(16,16),sprite.rect.size); Assert.AreEqual(FilterMode.Point,sprite.texture.filterMode);
                Assert.AreEqual(12,sprite.pixelsPerUnit); Assert.Less(sprite.pivot.y,3,"Feet pivot must align with authoritative circle position.");
            }
        }
        [Test] public void ScannerRetainsSavedIdentifiersMetadataAndEvidenceWithoutInventingFacts()
        {
            // Explicit synthetic DTO tests for rendering; not provider verification.
            var view=new GameView {state=new GameState {cultural_context=new CulturalContext {links=new[]{new CulturalLink {
                seed=new CulturalEntity {entity_id="seed-test-only",name="Synthetic seed",category="artist"}, selected_id="film-test-only",setting="Original fictional room",
                recommendations=new[]{new CulturalEntity {entity_id="film-test-only",name="Synthetic film",category="movie",year=2001,tags=new[]{new CulturalTag{name="Test tag"}}}},
                evidence=new[]{new CulturalEvidence{origin="https://example.invalid",path="/fixture",body_sha256="test-digest",retrieved_at="test-time"}}
            }}}}};
            string text=GameUI.EvidenceText(view,true);
            foreach(string value in new[]{"LOCAL CAPTURE REPLAY","seed-test-only","film-test-only","Test tag","test-digest","fictional interpretation","not facts about your personality"})StringAssert.Contains(value,text);
            string control=GameUI.EvidenceText(view,true,false);StringAssert.Contains("AUTHORED CONTROL",control);StringAssert.Contains("Invented",control);StringAssert.DoesNotContain("Synthetic film",control);
            Assert.AreEqual("film-test-only",view.state.cultural_context.links[0].selected_id,"Comparison must never mutate saved context.");
        }
        [Test] public void AuthoredScannerCannotPresentInventedCulturalEvidence()
        {
            var text=GameUI.EvidenceText(new GameView{state=new GameState()},false);
            StringAssert.Contains("no Qloo cultural evidence",text);
        }
    }
}
