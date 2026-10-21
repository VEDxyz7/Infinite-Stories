using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace InfiniteStories.Tests
{
    public sealed class PresentationTests
    {
        [UnityTest] public IEnumerator ContextDrawersReframeTheWorldAndRestoreTheSameConfirmedState()
        {
            var root=new GameObject("Player composition test");var ui=root.AddComponent<GameUI>();ui.Initialize();
            var state=new GameState{flags=new string[0],history=new[]{"The night begins."},visits=1,ending=""};
            var view=new GameView{session_id="presentation-test",state=state,location=new Location{id="quay",name="Side A"},nearby=new WorldObject[0],objectives=new Objective[0],narrative="The night begins."};
            ui.ShowGame(view);Assert.AreEqual(.735f,ui.WorldViewport.height);Assert.AreEqual(1,ui.WorldViewport.width);
            ui.ShowJournal();Assert.AreEqual(.60f,ui.WorldViewport.width);Assert.IsTrue(ui.Blocking);Assert.AreEqual(1,state.visits);
            ui.ShowGame(view);Assert.AreEqual(1,ui.WorldViewport.width);Assert.IsFalse(ui.Blocking);
            ui.ShowDialogue(view,new WorldObject{id="mara",name="Mara",kind="npc",text="An authored clue."},_=>{});
            Assert.AreEqual(.32f,ui.WorldViewport.y);ui.CloseDialogue();Assert.AreEqual(.18f,ui.WorldViewport.y);
            Assert.AreEqual("The night begins.",ui.StoryText);Object.Destroy(root);yield return null;
        }
        [UnityTest] public IEnumerator ReturningToTitleHidesTheWorldAndResumeRestoresItsCamera()
        {
            var root=new GameObject("Title camera regression");var ui=root.AddComponent<GameUI>();ui.Initialize();var world=root.AddComponent<TileWorld>();
            var rows=new string[18];for(int i=0;i<18;i++)rows[i]=new string('0',32);
            var place=new Location{id="quay",name="Side A",width=32,height=18,rows=rows,objects=new WorldObject[0]};
            var view=new GameView{session_id="camera-test",state=new GameState{flags=new string[0],history=new string[0],ending="",visits=1},location=place,nearby=new WorldObject[0],objectives=new Objective[0]};
            world.Show(place,4,5);ui.ShowGame(view);yield return null;var camera=Camera.main;Assert.IsNotNull(camera);Assert.IsTrue(camera.enabled);
            ui.ShowTitle(true);yield return null;Assert.IsFalse(camera.enabled,"Saved world must not show through title artwork.");
            ui.ShowGame(view);yield return null;Assert.IsTrue(camera.enabled,"Resuming must restore the same cached world camera.");
            Object.Destroy(root);yield return null;
        }
        [UnityTest] public IEnumerator BreathingAndInteractionNeverMoveThePhysicsAnchor()
        {
            var go=new GameObject("Idle presentation test");var motor=go.AddComponent<PlayerMotor>();motor.Restore(4,5);motor.CanMove=false;
            var actor=go.GetComponent<CityCharacter>();actor.Emphasize();
            yield return new WaitForSecondsRealtime(.15f);
            var silhouette=go.transform.Find("Animated silhouette");Assert.IsNotNull(silhouette);
            float y=silhouette.localPosition.y;yield return new WaitForSecondsRealtime(.4f);
            Assert.AreNotEqual(y,silhouette.localPosition.y,"Standing source pose must have subtle original breathing motion.");
            Assert.That(Vector2.Distance(motor.Position,new Vector2(4,5)),Is.LessThan(.01f));
            Assert.AreEqual(.28f,go.GetComponent<CircleCollider2D>().radius);
            Object.Destroy(go);
        }
        [UnityTest] public IEnumerator FurnishingsRespectSolidFootprintsAndGateReflectsOnlyConfirmedTokens()
        {
            string[] rows=new string[18];for(int y=0;y<18;y++){rows[y]="";for(int x=0;x<32;x++)rows[y]+=x==0||x==31||y==0||y==17||(x>=7&&x<=10&&y>=11&&y<=14)?"1":"0";}
            foreach(string id in new[]{"quay","market","archive","station"}){
                var go=new GameObject("Interior footprint test");var f=go.AddComponent<VenueFurniture>();var place=new Location{id=id,width=32,height=18,rows=rows};f.Build(place);
                var pieces=go.GetComponentsInChildren<FurnitureFootprint>();Assert.GreaterOrEqual(pieces.Length,16);
                foreach(var piece in pieces)Assert.IsTrue(VenueFurniture.IsSolid(place,piece.Cell.x,piece.Cell.y));
                f.Confirm(new GameState{flags=new[]{"map"}});
                Assert.IsFalse(VenueFurniture.IsSolid(place,14,9),"Resident's interaction approach must stay clear.");
                Object.Destroy(go);yield return null;
            }
        }
    }
}
