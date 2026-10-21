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
        [Test] public void ScannerToolsAreReadOnlyGroundedAndQueryOnlySavedNames()
        {
            // Synthetic rendering DTO, never live-provider evidence.
            var seed=new CulturalEntity{entity_id="seed-test",name="Example artist",category="artist"};
            var result=new CulturalEntity{entity_id="result-test",name="Example film",category="movie",tags=new CulturalTag[0]};
            var state=new GameState{flags=new[]{"trace_0"},visits=4,cultural_context=new CulturalContext{rule_version="cultural-investigation-v2",links=new[]{new CulturalLink{seed=seed,recommendations=new[]{result},selected_id=result.entity_id,setting="Fictional stage",evidence=new CulturalEvidence[0]}}}};
            var view=new GameView{state=state};string before=JsonUtility.ToJson(state);
            StringAssert.Contains("Example artist",GameUI.ScannerText(view,0,"ARTIST",true));
            StringAssert.DoesNotContain("Example film",GameUI.ScannerText(view,0,"ARTIST",true));
            StringAssert.Contains("No saved entity matches",GameUI.ScannerText(view,0,"no-such-entity",true));
            StringAssert.Contains("Example artist -> Example film",GameUI.ScannerText(view,1,"",true));
            StringAssert.Contains("result-test",GameUI.ScannerText(view,2,"",true));
            string progress=GameUI.ScannerText(view,3,"",true);
            StringAssert.Contains("CONFIRMED · Ivo",progress);StringAssert.Contains("MISSING · Sera",progress);
            StringAssert.Contains("currently allowed server choice",GameUI.ScannerText(view,4,"",true));
            Assert.AreEqual(before,JsonUtility.ToJson(state));
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
            string player=GameUI.EvidenceText(view,true,true,false);
            StringAssert.Contains("REPLAY PREVIEW",player);StringAssert.Contains("Synthetic film",player);
            foreach(string value in new[]{"seed-test-only","film-test-only","test-digest","https://example.invalid"})StringAssert.DoesNotContain(value,player);
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
