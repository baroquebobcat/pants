package org.pantsbuild.tools.junit.lib;

import org.junit.After;
import org.junit.AfterClass;
import org.junit.Before;
import org.junit.BeforeClass;
import org.junit.Test;

public class SecBoundarySystemExitTests {

  @BeforeClass
  public static void beforeAll() {
    System.out.println("=before class.");
  }

  @AfterClass
  public static void afterAll() {
    System.out.println("=after class.");
  }

  @Before
  public void beforeEach() {
    System.out.println("==before.");
  }

  @After
  public void afterEach() {
    System.out.println("==after.");
  }

  @Test
  public void directSystemExit() {
    System.exit(0);
  }

  // this test should still fail
  @Test
  public void catchesSystemExit() {
    try {
      System.exit(0);
    } catch (RuntimeException e) {
      // ignore
    }
  }

  @Test
  public void exitInJoinedThread() throws Exception {
    Thread thread = new Thread(new Runnable() {
      @Override
      public void run() {
        System.exit(0);
      }
    });
    thread.start();
    thread.join();
  }

  @Test
  public void exitInNotJoinedThread() {
    Thread thread = new Thread(new Runnable() {
      @Override
      public void run() {
        try {
          Thread.sleep(4); // wait for test to finish.
        } catch (InterruptedException e) {
          e.printStackTrace();
        }
        System.out.println("dangling thread now exiting");
        System.exit(0);
      }
    });
    thread.start();
  }

  // The system exit failure should not be attributed to this test.
  @Test
  public void justSleeps() throws InterruptedException {
    Thread.sleep(10);
  }
}
