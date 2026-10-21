using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace InfiniteStories.Tests
{
    public sealed class MovementTests
    {
        [UnityTest] public IEnumerator FourDirectionsAndTilemapBoundariesUseRealPhysics()
        {
            var root=new GameObject("Physics boundary test");
            var world=root.AddComponent<TileWorld>();
            var area=new Location { id="test-only-boundary",name="Isolated collision test",width=8,height=8,
                rows=new[] { "11111111","10000001","10000001","10000001","10000001","10000001","10000001","11111111" },
                objects=System.Array.Empty<WorldObject>() };
            try
            {
                world.Show(area,4,4);
                yield return null; yield return new WaitForFixedUpdate();
                var motor=world.Player; motor.CanMove=true;
                Vector2[] directions={Vector2.up,Vector2.down,Vector2.left,Vector2.right};
                foreach (Vector2 direction in directions)
                {
                    motor.StopInput(); motor.Restore(4,4); motor.Nudge(direction);
                    yield return new WaitForSecondsRealtime(.5f);
                    Assert.Greater(Vector2.Dot(motor.Position-new Vector2(4,4),direction),.5f,
                        "Every accessible direction must move the real Rigidbody2D.");
                }
                Vector2[] starts={new Vector2(4,6),new Vector2(4,1),new Vector2(1,4),new Vector2(6,4)};
                for (int i=0;i<directions.Length;i++)
                {
                    motor.StopInput(); motor.Restore(starts[i].x,starts[i].y); motor.Nudge(directions[i]);
                    yield return new WaitForSecondsRealtime(.5f);
                    Assert.That(motor.Position.x,Is.InRange(.77f,6.23f));
                    Assert.That(motor.Position.y,Is.InRange(.77f,6.23f),
                        "Tilemap colliders must stop the avatar's radius at each solid boundary.");
                }
            }
            finally { UnityEngine.Object.Destroy(root); }
        }

        [Test] public void AccessibleInputReachesPhysicsBeforeTheNextRenderUpdate()
        {
            var go=new GameObject("Accessible input timing"); var motor=go.AddComponent<PlayerMotor>();
            motor.CanMove=true; motor.Nudge(Vector2.right);
            // Background browsers can run catch-up physics before the next Update.
            motor.SendMessage("FixedUpdate");
            Assert.Greater(go.GetComponent<Rigidbody2D>().linearVelocity.x,0);
            motor.CanMove=false; motor.SendMessage("FixedUpdate");
            Assert.AreEqual(Vector2.zero,go.GetComponent<Rigidbody2D>().linearVelocity);
            UnityEngine.Object.Destroy(go);
        }
        [UnityTest] public IEnumerator RestoreStopsMovementAndPausedPlayerRemainsStill()
        {
            var go=new GameObject("Test traveler"); var motor=go.AddComponent<PlayerMotor>();
            motor.Restore(4,5); motor.CanMove=false;
            yield return new WaitForFixedUpdate(); yield return new WaitForFixedUpdate();
            Assert.That(Vector2.Distance(motor.Position,new Vector2(4,5)),Is.LessThan(.01f));
            Assert.That(go.GetComponent<Rigidbody2D>().linearVelocity.sqrMagnitude,Is.LessThan(.001f));
            UnityEngine.Object.Destroy(go);
        }
    }
}
