using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.Tilemaps;

namespace InfiniteStories.Tests
{
    public sealed class UrbanRenderingTests
    {
        [UnityTest] public IEnumerator ImportedWalkFramesPlayAndFollowFeetDepth()
        {
            var go=new GameObject("Imported actor animation check",typeof(SpriteRenderer));var actor=go.AddComponent<CityCharacter>();actor.Actor=3;
            var frames=new HashSet<Sprite>();
            for(int i=0;i<12;i++){actor.Pose(Vector2.left,true);frames.Add(go.GetComponent<SpriteRenderer>().sprite);yield return new WaitForSecondsRealtime(.06f);}
            Assert.GreaterOrEqual(frames.Count,3,"Standing and both real walking poses must play.");
            go.transform.position=new Vector3(5,10,0);yield return null;int behind=go.GetComponent<SpriteRenderer>().sortingOrder;
            go.transform.position=new Vector3(5,8,0);yield return null;Assert.Greater(go.GetComponent<SpriteRenderer>().sortingOrder,behind);
            Object.Destroy(go);
        }
        [UnityTest] public IEnumerator ImportedSpritesSurviveAreaCleanupAndCollisionRowsRemainAuthoritative()
        {
            var root=new GameObject("Urban world cleanup test");var world=root.AddComponent<TileWorld>();
            var place=new Location{id="quay",name="Test area",width=8,height=8,objects=System.Array.Empty<WorldObject>(),rows=new[]{"11111111","10000001","10000001","10000001","10000001","10000001","10000001","11111111"}};
            world.Show(place,4,4);yield return null;
            var walls=root.transform.Find("Test area/Stone").GetComponent<Tilemap>();Assert.IsNotNull(walls.GetComponent<TilemapCollider2D>());
            Assert.IsTrue(walls.HasTile(Vector3Int.zero));Assert.IsFalse(walls.HasTile(new Vector3Int(4,4,0)));
            var source=NightArt.Character(0,1,0);Assert.IsNotNull(Camera.main.GetComponent<AudioListener>());
            foreach(string cue in new[]{"click_001","confirmation_001","open_001"}){var clip=Resources.Load<AudioClip>("Art/Audio/"+cue);Assert.IsNotNull(clip);Assert.Greater(clip.samples,0);}
            world.Clear();yield return null;Assert.IsNotNull(source,"Area cleanup must never destroy shared imported sprite assets.");
            Assert.IsNotNull(NightArt.Character(0,1,0));Object.Destroy(root);
        }
    }
}
